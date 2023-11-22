import models
import csv
import shutil
from subprocess import call
from fastapi import FastAPI, Request, Depends, BackgroundTasks, Form
from fastapi.responses import HTMLResponse
from typing_extensions import Annotated
from fastapi.templating import Jinja2Templates
from database import SessionLocal, engine
from sqlalchemy.orm import Session
from sqlalchemy import func, text, select, delete
from pydantic import BaseModel
from models import Bet
from datetime import datetime

app = FastAPI()

models.Base.metadata.create_all(bind=engine)

templates = Jinja2Templates(directory="templates")

class BetRequest(BaseModel): 
    symbol: Annotated[str, Form(...)]

def get_db():
    try:
        db = SessionLocal()
        yield db 
    finally:
        db.close()


@app.get("/")
def home(request: Request, db: Session = Depends(get_db)):
   
    #displays the dashboard / homepage 
    
    bets = db.query(Bet).filter(Bet.active_flag == 'active')


    return templates.TemplateResponse("home.html", {
        "request": request,
        "bets": bets
    })

def fetch_bet_data(id: int):
    db = SessionLocal()

    ##### let users update their bet #### this could be a function
    mysubquery = db.query(
        Bet,
        func.rank().over(order_by=Bet.id.desc(),partition_by=['week','player_name']).label('rnk')).subquery()
    
    rows_to_delete = db.query(mysubquery).filter(mysubquery.c.rnk != 1).all()

    # Extract primary key values from rows
    ids_to_delete = [row[0] for row in rows_to_delete]

    # Delete rows not ranked as 1
    if ids_to_delete:
        db.query(Bet).filter(Bet.id.in_(ids_to_delete)).delete(synchronize_session=False)
 
    db.commit()

   ########## archive the old bets ##### this could be a function 
    if db.query(Bet.id).filter(Bet.active_flag == 'active').count() == 5 : 
        #print("greater than")
        db.query(Bet).filter(Bet.active_flag  == 'active').update({Bet.active_flag : 'archived'}, synchronize_session=False)
    #else:
        #print("less than")
    db.commit()


   ########## only let people make entries for the current week ## this could be a function
 
#            DELETE FROM bets
#            WHERE id = (SELECT MAX(id) FROM bets)
#            AND (week <> (SELECT MAX(week) FROM bets WHERE active_flag = 'old') + 1 or week <> (SELECT MAX(week) FROM bets where active_flag = 'active'));

    subquery = select(Bet.id).order_by(Bet.id.desc()).limit(1).as_scalar()
    subquery_old_week = select(Bet.week).where(Bet.active_flag == 'archived').order_by(Bet.week.desc()).limit(1).as_scalar()
    subquery_active_week = select(Bet.week).where(Bet.active_flag == 'active').order_by(Bet.week.desc()).limit(1).as_scalar()

    delete_query = delete(Bet).where(
        Bet.id == subquery
    ).where(
        ((Bet.week != (subquery_old_week + 1)) | (Bet.week != subquery_active_week))
    )

    try:
        result = db.execute(delete_query)
        db.commit()
        print(f"Affected rows: {result.rowcount}")
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
    finally:
        db.close()


    ########this could be a function
    bet = db.query(Bet).filter(Bet.id == id).first()
    
    try:
        bet.active_flag = 'active'
        db.add(bet)
        db.commit()
    except Exception as e:
        print('wrong week')
    

    ########## add active records to csv ### thiis could be a function 
    active_bets_query = db.query(Bet).filter(Bet.active_flag == 'active')
    active_bets_results = active_bets_query.all()

    # Write results to a CSV file
    output_file = 'output.csv'
    with open(output_file, 'w', newline='') as csvfile:
        csvwriter = csv.writer(csvfile)

        # Write header
        #csvwriter.writerow(['bet_type','week', 'player_name'])  # Add column names

        # Write data rows
        for result in active_bets_results:
            csvwriter.writerow([result.player_name,result.week,result.bet_type,result.winning_team,result.value])  # Add column values
    
    ######## create the variable cfg file from csv for send text ####
    input_csv_file = 'output.csv'

    # Output .cfg file name
    output_cfg_file = 'picks.cfg'

    # Read the CSV file and write to .cfg file
    with open(input_csv_file, mode='r') as csv_file, open(output_cfg_file, mode='w') as cfg_file:
        csv_reader = csv.reader(csv_file)
        
        for row in csv_reader:
            if len(row) == 5:
                name = row[0]
                data = ",".join(row)
                cfg_file.write(f'{name}="{data}"\n')

    print(f'Data has been copied to {output_cfg_file}.') 
    
    ########this could be its own function
    
    print(db.query(Bet.id).filter(Bet.active_flag == 'active').count())
    if db.query(Bet.id).filter(Bet.active_flag == 'active').count() == 5 : 
        

        ####### archive database - this could be its own function
        # Specify the source and destination file paths
        source_file = 'bets.db'
        destination_directory = 'db_archive/'  # Replace with your desired destination directory

        # Get the current timestamp
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')

        # Create the new filename by adding the timestamp
        destination_file = f'{timestamp}_{source_file}'

        # Copy the file to the destination directory with the new filename
        shutil.copy(source_file, f'{destination_directory}{destination_file}')

        print(f'File copied to: {destination_directory}{destination_file}')

        #send text !
        call("./send_text.sh")
        print('sent notification text message')

@app.post("/bet")
async def create_bet(background_tasks: BackgroundTasks, db: Session = Depends(get_db)
, bet_type: str = Form(...) 
, week: int = Form(...) 
, player_name: str = Form(...) 
, winning_team: str = Form(...) 
, losing_team: str = Form(...) 
, value: str = Form(...) 
):
    
    #creates a bet and stores it in the database   
    bet = Bet()
    bet.bet_type = bet_type
    bet.week = week
    bet.player_name = player_name
    bet.winning_team = winning_team
    bet.losing_team = losing_team
    bet.value = value


    db.add(bet)
    db.commit()

    background_tasks.add_task(fetch_bet_data, bet.id)


    return {
        "code": "success", 
        "message": "bet created"
    }


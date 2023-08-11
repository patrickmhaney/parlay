import models
from fastapi import FastAPI, Request, Depends, BackgroundTasks, Form
from fastapi.responses import HTMLResponse
from typing_extensions import Annotated
from fastapi.templating import Jinja2Templates
from database import SessionLocal, engine
from sqlalchemy.orm import Session
from pydantic import BaseModel
from models import Bet

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

    print(request)
    print(db)

    return templates.TemplateResponse("home.html", {
        "request": request,
        "bets": bets
    })

def fetch_bet_data(id: int):
    db = SessionLocal()
    bet = db.query(Bet).filter(Bet.id == id).first()

    bet.value = 20
    bet.active_flag = 'active'
    
    
    db.add(bet)
    db.commit()

    print("bet data fetched")
    print(db.query(Bet.id).count())
    print(db.query(Bet.id).filter(Bet.active_flag == 'active').count())
#try moving up 
    if db.query(Bet.id).filter(Bet.active_flag == 'active').count() > 5 : 
        print("greater than")
        db.query(Bet).filter(Bet.active_flag  == 'active').update({Bet.active_flag : 'old'}, synchronize_session=False)
    else:
        print("less than")


    db.commit()


@app.post("/bet")
async def create_bet(background_tasks: BackgroundTasks, db: Session = Depends(get_db)
, bet_type: str = Form(...) 
, player_name: str = Form(...) 
):
    
    #creates a bet and stores it in the database   
    bet = Bet()
    bet.bet_type = bet_type
    bet.player_name = player_name


    db.add(bet)
    db.commit()

    background_tasks.add_task(fetch_bet_data, bet.id)


    return {
        "code": "success", 
        "message": "bet created"
    }


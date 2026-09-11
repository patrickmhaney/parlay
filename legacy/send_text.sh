# RETIRED -- kept only for reference. Do not run.
#
# This script sourced picks.cfg, which was generated from user-submitted
# form input, so anything typed into the line field was executed by bash.
# The replacement is app/services/notify.py, which posts over HTTP and
# never touches a shell. The API key that used to be here is revoked
# and must be rotated; phone numbers now live in the users table.
#
#!/bin/bash

BASEDIR=$(dirname $(readlink -f ${0}))
. ${BASEDIR}/picks.cfg


#Ben
curl -X POST https://textbelt.com/text \
  --data-urlencode phone='REDACTED' \
  --data-urlencode message="The picks are in! 
-${Ben}
-${Leland}
-${Pat}
-${BD}
-${Hank}
http://www.parlaysyndicate.com" \
  -d key=${TEXTBELT_KEY}
#Leland
curl -X POST https://textbelt.com/text \
  --data-urlencode phone='REDACTED' \
  --data-urlencode message="The picks are in! 
-${Ben}
-${Leland}
-${Pat}
-${BD}
-${Hank}
http://www.parlaysyndicate.com" \
  -d key=${TEXTBELT_KEY}
#Pat
curl -X POST https://textbelt.com/text \
  --data-urlencode phone='REDACTED' \
  --data-urlencode message="The picks are in! 
-${Ben}
-${Leland}
-${Pat}
-${BD}
-${Hank}
http://www.parlaysyndicate.com" \
  -d key=${TEXTBELT_KEY}
#BD
curl -X POST https://textbelt.com/text \
  --data-urlencode phone='REDACTED' \
  --data-urlencode message="The picks are in! 
-${Ben}
-${Leland}
-${Pat}
-${BD}
-${Hank}
http://www.parlaysyndicate.com" \
  -d key=${TEXTBELT_KEY}
#Hank
curl -X POST https://textbelt.com/text \
  --data-urlencode phone='REDACTED' \
  --data-urlencode message="The picks are in! 
-${Ben}
-${Leland}
-${Pat}
-${BD}
-${Hank}
http://www.parlaysyndicate.com" \
  -d key=${TEXTBELT_KEY}

# RETIRED -- kept only for reference. Do not run.
# The Textbelt key that was here is revoked and must be rotated.
#!/bin/bash

BASEDIR=$(dirname $(readlink -f ${0}))
. ${BASEDIR}/picks.cfg

all_the_picks=${Ben}${Leland}${Pat}${BD}${Hank}
curl -X POST https://textbelt.com/text \
  --data-urlencode phone='REDACTED' \
  --data-urlencode message="The picks are in! 
${all_the_picks}" \
  -d key=${TEXTBELT_KEY}

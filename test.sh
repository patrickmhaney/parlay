#!/bin/bash

BASEDIR=$(dirname $(readlink -f ${0}))
. ${BASEDIR}/picks.cfg

all_the_picks=${Ben}${Leland}${Pat}${BD}${Hank}
curl -X POST https://textbelt.com/text \
  --data-urlencode phone='5139108729' \
  --data-urlencode message="The picks are in! 
${all_the_picks}" \
  -d key=9b9bf9d43b8103c904e702c11257fed6c6ba3de48TV04t4ld2xpudpNMukLme8N6

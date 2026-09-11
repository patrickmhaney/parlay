# RETIRED -- kept only for reference. Do not run.
# The Textbelt key that was here is revoked and must be rotated.
import requests

resp = requests.post('https://textbelt.com/text', {
    'phone': 'REDACTED',
  'message': 'Hello world',
  'key': '${TEXTBELT_KEY}',
})
print(resp.json())

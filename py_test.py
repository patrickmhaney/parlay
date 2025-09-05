import requests

resp = requests.post('https://textbelt.com/text', {
    'phone': '5139108729',
  'message': 'Hello world',
  'key': '9b9bf9d43b8103c904e702c11257fed6c6ba3de48TV04t4ld2xpudpNMukLme8N6',
})
print(resp.json())

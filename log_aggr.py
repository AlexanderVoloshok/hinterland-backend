from pandas import DataFrame, concat
from dateutil.parser import parse
from config import ENGINE


def is_date(string, fuzzy=False):
    """
    Return whether the string can be interpreted as a date.

    :param string: str, string to check for date
    :param fuzzy: bool, ignore unknown tokens in string if True
    """
    try: 
        parse(string, fuzzy=fuzzy)
        return True
    except ValueError:
        return False


def extract_from_url(url):
	if not url.startswith("/api"):
		return url
	a = url.split("/")
	try:
		fid = int(a[-1])
		a[-1] = "<fid>"
	except ValueError:
		if a[-2] == 'search_parcels':
			a[-1] = "<pattern>"
	link = "/".join(a).replace("/api/", "")
	return link


path = 'D:/Angular/Лилов диплом/hinterland-backend/server-logs.log'

dics = []
with open(path) as file:
	for row in file.readlines():
		l = row.split()
		if "end:" in row and len(l) >= 12:
			url = l[8].split("/")
			a = {
			    "date": parse(l[1], fuzzy=False), 
			    "time": l[2], 
			    "ip": l[5], 
			    "route": url[-1], 
				'city': url[2] if len(url) > 2 else None,
			    "status": int(l[-3]), 
			    "length": float(l[-1][:-1]),
			    "is_bot": not l[8].startswith("/api")
			}
			dics.append(a)

df = DataFrame.from_records(dics).drop_duplicates()
df.to_excel('D:/Angular/Лилов диплом/hinterland-backend/server-logs.xlsx')
print('%s rows collected' % df.shape[0])
#if df.shape[0] > 0:
#    with open(path, "w"):
#        pass
    
#df.to_sql('api_statistics', con=ENGINE, schema='statistics', if_exists='append',index=False)
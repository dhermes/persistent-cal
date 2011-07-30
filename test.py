from icalendar import Calendar
import pickle
from urllib2 import urlopen
from urllib2 import urlparse

def pickle_event(event):
  # all events have a UID, and almost all begin with 'item-';
  # those that don't are an away event for the entire trip
  uid = unicode(event.get('uid'))
  to_pickle = {'when:from': event.get('dtstart').dt,
               'when:to': event.get('dtend').dt,
               'summary': unicode(event.get('summary')),
               'location': unicode(event.get('location')),
               'description': unicode(event.get('description'))}
  return uid, pickle.dumps(to_pickle)

link = ('webcal://www.tripit.com/feed/ical/private/'
        '3F43994D-4591D1AA4C63B1472D8D5D0E9568E5A8/tripit.ics')
link = 'http:%s ' % urlparse.urlparse(link).path

feed = urlopen(link)
request_headers = feed.headers.dict
last_modified = request_headers['last-modified'] # trip it doesn't respect this
cal_feed = feed.read()
feed.close()

ical = Calendar.from_string(cal_feed)
name = unicode(ical.get('X-WR-CALNAME'))
for component in ical.walk():
  if component.name == "VEVENT":
    uid, pickle_contents = pickle_event(component)
    print uid

# GCal -> iCal correspondences:
# - title -> summary
# - when:from -> dtstart
# - when:to -> dtend
# - where -> location
# - calendar -> None
# - description -> description
# - reminders -> None
# Note: geo gives but who knows what for lat and lng


## Event stuff
# e = Event(key_name='item-a218099f87f84bb18818b575b345d9333d4260aa@tripit.com',
#           owners=['a','b','c'],
#           event_data = 'a')
# e.put()
# e = Event.all().get()
# e.owners.append('a')
# e.put()


# use
# Event(key_name=uid, ...)

## GDATA STUFF

# import gdata.calendar.client
# from secret_key import CONSUMER_KEY
# from secret_key import CONSUMER_SECRET
# gcal = gdata.calendar.client.CalendarClient(source='persistent-cal')
# scopes = ['https://www.google.com/calendar/feeds/']
# oauth_callback = 'http://persistent-cal.appspot.com/verify'
# consumer_key = CONSUMER_KEY
# consumer_secret = CONSUMER_SECRET
# request_token = gcal.get_oauth_token(scopes, oauth_callback,
#                                      consumer_key, consumer_secret)
# # go to https://www.google.com/accounts/b/0/OAuthAuthorizeToken?oauth_token=<request_token.token>&hd=default
# # then authorize then click accept and copy over the query_params
# q_params = '?oauth_verifier=LedqJ48lfEjjx8GzSS6aRP57&oauth_token=4%2Flhat8tWEndklLt7gz8jN7rK8pEO6'
# gdata.gauth.authorize_request_token(request_token, '%s%s' % (oauth_callback, q_params))
# gcal.auth_token = gcal.get_access_token(request_token)

# a = gcal.GetAllCalendarsFeed()
# # let users choose index from [xx.title.text for xx in a.entry]
# cal_index = 1
# uri = a.entry[cal_index].link[0].href
# if uri.startswith('http:'):
#   uri = 'https%s' % uri[4:]
# feed = gcal.GetCalendarEventFeed(uri=uri)
# for i, an_event in enumerate(feed.entry):
#   print '\t%s. %s' % (i, an_event.title.text,)


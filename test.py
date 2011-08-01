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
# # sharona
# link = ('webcal://www.tripit.com/feed/ical/private/'
#         '4A025929-DCB74CB87F330487615696811896215A/tripit.ics')
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
# danny_ical = [unicode(xx.get('uid')) for xx in ical.walk()
#               if xx.name == "VEVENT"]
# roni_ical = [unicode(xx.get('uid')) for xx in ical.walk()
#              if xx.name == "VEVENT"]

# GCal -> iCal correspondences:
# - title.text -> summary
# - when[0].start -> dtstart
# - when[0].end -> dtend
# - where[0].value -> location
# - calendar -> None
# - content.text -> description
# - when[0].reminder -> None
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

import gdata.calendar.client
from secret_key import CONSUMER_KEY
from secret_key import CONSUMER_SECRET
gcal = gdata.calendar.client.CalendarClient(source='persistent-cal')
scopes = ['https://www.google.com/calendar/feeds/']
oauth_callback = 'http://persistent-cal.appspot.com/verify'
consumer_key = CONSUMER_KEY
consumer_secret = CONSUMER_SECRET
request_token = gcal.get_oauth_token(scopes, oauth_callback,
                                     consumer_key, consumer_secret)
token_data = {'auth_state': 3,
              'next': None,
              'token': '1/suaZl-xTHz5hykuUb6RAYEkN7YamCVv6hfsxJzKivSY',
              'token_secret': 'sLCasckqtSUmFv-KHPYb27zf',
              'verifier': None}
for key, value in token_data.items():
  setattr(request_token, key, value)
gcal.auth_token = request_token

# # # BEEP # # #
# event = gdata.calendar.data.CalendarEventEntry()
# import atom
# event.title = atom.data.Title(text='Test')
# event.content = atom.data.Content(text='Test content')
# where='On the courts'
# event.where.append(gdata.calendar.data.CalendarWhere(value=where))
# start_time = '2011-08-01T22:00:00.000Z'
# end_time = '2011-08-01T23:00:00.000Z'
# # %Y-%m-%dT%H:%M:%S.000Z
# # start_time = time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime())
# # .... returns '2011-07-31T23:44:54.000Z' (in UTC)
# # whereas my things have format
# # 2011-08-01T08:00:00.000-07:00
# event.when.append(gdata.calendar.data.When(start=start_time, end=end_time))
# new_event = gcal.InsertEvent(event)
# print new_event.id.text
# # # BEEP # # #

# # === OLD WAY ===
# # go to https://www.google.com/accounts/b/0/OAuthAuthorizeToken?
# #           hd=default&oauth_token=<request_token.token>
# # then authorize then click accept and copy over the query_params
# q_params = '?oauth_verifier=YOPXUEaGgfaWPDbw6cMYhgko&oauth_token=4%2F90TvjZW4WaTxNWGcnCu3ombri-an'
# gdata.gauth.authorize_request_token(request_token, '%s%s' % (oauth_callback, q_params))
# gcal.auth_token = gcal.get_access_token(request_token)
# # === OLD WAY ===

a = gcal.GetAllCalendarsFeed()
# let users choose index from [xx.title.text for xx in a.entry]
cal_index = 1
uri = a.entry[cal_index].link[0].href # .get_self_link()
if uri.startswith('http:'):
  uri = 'https%s' % uri[4:]
feed = gcal.GetCalendarEventFeed(uri=uri)
for i, an_event in enumerate(feed.entry):
  print '\t%s. %s' % (i, an_event.title.text,)

feed = gcal.GetCalendarEventFeed()
print 'Events on Primary Calendar: %s' % (feed.title.text,)
for i, an_event in enumerate(feed.entry):
  print '\t%s. %s' % (i, an_event.title.text,)
  for p, a_participant in enumerate(an_event.who):
    print '\t\t%s. %s' % (p, a_participant.email,)
    if a_participant.attendee_status is not None:
      print '\t\t\t%s' % (a_participant.attendee_status.value,)
    else:
      print '\t\t\t%s' % ('No status',)


#############################
# daniel.j.hermes@gmail.com #
#############################
# {'auth_state': 1,
#  'consumer_key': 'persistent-cal.appspot.com',
#  'consumer_secret': 'SF7IeKf2olrEAYKzj6NSPR9U',
#  'next': None,
#  'token': '4/BSbwDH19fWTYuT0iRchcnut9EjHz',
#  'token_secret': 'anWqxwuuhqazbbwpcX_1teT2',
#  'verifier': None}

# ?oauth_verifier=cs-aI1nEkhyqHjVg5InR1q1X&oauth_token=4%2FBSbwDH19fWTYuT0iRchcnut9EjHz

# {'auth_state': 2,
#  'consumer_key': 'persistent-cal.appspot.com',
#  'consumer_secret': 'SF7IeKf2olrEAYKzj6NSPR9U',
#  'next': None,
#  'token': '4/BSbwDH19fWTYuT0iRchcnut9EjHz',
#  'token_secret': 'anWqxwuuhqazbbwpcX_1teT2',
#  'verifier': 'cs-aI1nEkhyqHjVg5InR1q1X'}

# {'auth_state': 3,
#  'consumer_key': 'persistent-cal.appspot.com',
#  'consumer_secret': 'SF7IeKf2olrEAYKzj6NSPR9U',
#  'next': None,
#  'token': '1/suaZl-xTHz5hykuUb6RAYEkN7YamCVv6hfsxJzKivSY',
#  'token_secret': 'sLCasckqtSUmFv-KHPYb27zf',
#  'verifier': None}

############################
# dhermes@bossylobster.com #
############################
# {'auth_state': 1,
#  'consumer_key': 'persistent-cal.appspot.com',
#  'consumer_secret': 'SF7IeKf2olrEAYKzj6NSPR9U',
#  'next': None,
#  'token': '4/90TvjZW4WaTxNWGcnCu3ombri-an',
#  'token_secret': 'ZyedHs0am9Z8MqrsCbZN678d',
#  'verifier': None}

# {'auth_state': 2,
#  'consumer_key': 'persistent-cal.appspot.com',
#  'consumer_secret': 'SF7IeKf2olrEAYKzj6NSPR9U',
#  'next': None,
#  'token': '4/90TvjZW4WaTxNWGcnCu3ombri-an',
#  'token_secret': 'ZyedHs0am9Z8MqrsCbZN678d',
#  'verifier': 'YOPXUEaGgfaWPDbw6cMYhgko'}

# {'auth_state': 3,
#  'consumer_key': 'persistent-cal.appspot.com',
#  'consumer_secret': 'SF7IeKf2olrEAYKzj6NSPR9U',
#  'next': None,
#  'token': '1/iLuG70qpK2UZu0Ct9hQrGeV_L-OMEXbUZs5tIo5wWjs',
#  'token_secret': 'TIHutZun2wQiJiG7DnrU0KdH',
#  'verifier': None}

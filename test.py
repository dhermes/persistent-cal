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


# Event model
# from google.appengine.ext import db


# class Event(db.Model):
#   """Holds data for a calendar event (including shared owners)"""
#   owners = db.StringListProperty(required=True) # hold owner id's as strings
#   event_data = db.TextProperty(required=True) # will be python dict in pickle

# e = Event(key_name='item-a218099f87f84bb18818b575b345d9333d4260aa@tripit.com',
#           owners=['a','b','c'],
#           event_data = 'a')
# e.put()
#     e = Event.all().get()
#     e.owners.append('a')
#     e.put()


# use
# Event(key_name=uid, ...)

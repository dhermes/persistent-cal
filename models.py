from google.appengine.ext import db

class Event(db.Model):
  """Holds data for a calendar event (including shared attendees)"""
  who = db.StringListProperty(required=True)  # hold owner ids as strings
  event_data = db.TextProperty(required=True)  # python dict as simplejson
  gcal_edit = db.StringProperty(required=True)


class UserCal(db.Model):
  """Holds data for a calendar event (including shared owners)"""
  owner = db.UserProperty(required=True)
  # hold public calendar link as strings
  calendars = db.StringListProperty(required=True)
  # http://code.google.com/appengine/docs/python/datastore/...
  #     ...typesandpropertyclasses.html#ListProperty
  # (int defaults to long, so I'll use long)
  update_intervals = db.ListProperty(long, required=True)

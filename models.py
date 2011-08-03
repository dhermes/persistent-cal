from google.appengine.ext import db

class Event(db.Model):
  """Holds data for a calendar event (including shared attendees)"""
  who = db.StringListProperty(required=True)  # hold owner ids as strings
  event_data = db.TextProperty(required=True)  # will be python dict in pickle
  gcal_edit = db.StringProperty(required=True)


class UserCal(db.Model):
  """Holds data for a calendar event (including shared owners)"""
  owner = db.UserProperty(required=True)
  # hold public calendar link as strings
  calendars = db.StringListProperty(required=True)
  # http://code.google.com/appengine/docs/python/datastore/...
  #     ...typesandpropertyclasses.html#ListProperty
  update_intervals = db.ListProperty(int, default=[], required=True)

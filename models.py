from google.appengine.ext import db

class Event(db.Model):
  """Holds data for a calendar event (including shared owners)"""
  owners = db.StringListProperty(required=True)  # hold owner id's as strings
  event_data = db.TextProperty(required=True)  # will be python dict in pickle

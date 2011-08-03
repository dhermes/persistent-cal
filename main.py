# General libraries
import os
from datetime import datetime
import pickle
import simplejson
from urllib2 import urlopen
from urllib2 import urlparse

# Third-party libraries
import atom
import gdata.gauth
import gdata.calendar.client
from icalendar import Calendar

# App engine specific libraries
from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import login_required
from google.appengine.ext.webapp.util import run_wsgi_app

# App specific libraries
from models import Event
from models import UserCal
from secret_key import CONSUMER_KEY
from secret_key import CONSUMER_SECRET
from secret_key import TOKEN
from secret_key import TOKEN_SECRET


# Create an instance of the DocsService to make API calls
AUTH_TOKEN = gdata.gauth.OAuthHmacToken(consumer_key=CONSUMER_KEY,
                                        consumer_secret=CONSUMER_SECRET,
                                        token=TOKEN,
                                        token_secret=TOKEN_SECRET,
                                        auth_state=3)
GCAL = gdata.calendar.client.CalendarClient(source='persistent-cal')
GCAL.auth_token = AUTH_TOKEN

URI = ('https://www.google.com/calendar/feeds/'
       'vhoam1gb7uqqoqevu91liidi80%40group.calendar.google.com/private/full')
# FEED = GCAL.GetCalendarEventFeed(uri=URI)

def FormatTime(time_value):
  # Currently only expecting datetime.datetime or datetime.date

  # strftime('%Y-%m-%dT%H:%M:%S.000Z')
  # works with both date and datetime instances
  time_parse = '%Y-%m-%d'
  if type(time_value) == datetime:
    # Default is UTC/GMT
    time_parse += 'T%H:%M:%S.000Z'
  return time_value.strftime(time_parse)


def ParseEvent(event):
  # Assumes event is type icalendar.cal.Event
  
  # all events have a UID, and almost all begin with 'item-';
  # those that don't are an away event for the entire trip
  uid = unicode(event.get('uid'))
  description = unicode(event.get('description'))
  location = unicode(event.get('location'))
  # # WITNESS:
  # 4754cd75888cac4a53c7cf003980e195b46dc9fd@tripit.com
  # via 3F43994D-4591D1AA4C63B1472D8D5D0E9568E5A8/tripit.ics
  # description: Daniel Hermes is in San Diego, CA from Sep 1...
  # and via 4A025929-DCB74CB87F330487615696811896215A/tripit.ics
  # description: Sharona Franko is in San Diego, CA from Sep 1...
  if not uid.startswith('item-'):
    target = ' is in %s ' % location
    if description.count(target) != 1:
      # TODO(dhermes) log and fail silently
      raise Exception('Unrecognized event format')

    description = 'In %s %s' % (location, description.split(target)[1])

  event_data = {'when:from': event.get('dtstart').dt,
                'when:to': event.get('dtend').dt,
                'summary': unicode(event.get('summary')),
                'location': location,
                'description': description}
  return uid, event_data


def ConvertToInterval(timestamp):
  # Monday 0, sunday 6
  # 8 intervals in a day, round up hours
  interval = 8*timestamp.weekday() + timestamp.hour/3 + 1

  # If we are exactly on an hour that is a multiple of three
  # we do not wish to round up since floor(x) == ceil(x), contrary
  # to all other cases where ceil(x) == floor(x) + 1
  if (timestamp.hour % 3 == 0 and timestamp.minute == 0 and
      timestamp.second == 0 and timestamp.microsecond == 0):
    interval -= 1

  return interval % 56


def AddOrUpdateEvent(event_data, event=None, push_update=True):
  # Create event in user's calendar
  update = (event is not None)
  if not update:
    event = gdata.calendar.data.CalendarEventEntry()

  event.title = atom.data.Title(text=event_data['summary'])
  event.content = atom.data.Content(text=event_data['description'])

  # Where
  event.where.append(gdata.calendar.data.CalendarWhere(
      value=event_data['location']))

  # When
  start_time = FormatTime(event_data['when:from'])
  end_time = FormatTime(event_data['when:to'])
  event.when.append(gdata.calendar.data.When(start=start_time, end=end_time))

  if update:
    if push_update:
      # TODO(dhermes) see if possible to manage this from feed
      GCAL.Update(event)
    return event
  else: 
    # Who
    who_add = gdata.calendar.data.EventWho(email=event_data['email'])
    event.who.append(who_add)

    # TODO(dhermes) see if possible to manage this from feed
    new_event = GCAL.InsertEvent(event, insert_uri=URI)
    return new_event


def UpdateSubcription(link, current_user):
  current_user_id = current_user.user_id()

  import_feed = urlopen(link)
  ical = Calendar.from_string(import_feed.read())
  import_feed.close()

  for component in ical.walk():
    # TODO(dhermes) add calendar name to event data
    if component.name == "VEVENT":
      uid, event_data = ParseEvent(component)
      event = Event.get_by_key_name(uid)
      if event is None:
        # Create new event
        # (leaving out the event argument creates a new event)
        event_data['email'] = current_user.email()
        cal_event = AddOrUpdateEvent(event_data)

        gcal_edit = cal_event.get_edit_link().href
        event = Event(key_name=uid,
                      who=[current_user_id],  # id is string
                      event_data=db.Text(pickle.dumps(event_data)),
                      gcal_edit=gcal_edit)
        event.put()
      else:
        # We need to make changes for new event data or a new owner
        if (current_user_id not in event.who or
            db.Text(pickle.dumps(event_data)) != event.event_data):
          # Grab GCal event to edit
          # TODO(dhermes) see if possible to manage this from feed
          cal_event = GCAL.GetEventEntry(uri=event.gcal_edit)

          # Update who
          if current_user_id not in event.who:
            event.who.append(current_user_id)  # id is string

            # add existing event to current_user's calendar
            who_add = gdata.calendar.data.EventWho(email=current_user.email())
            cal_event.who.append(who_add)

          # Update existing event
          if db.Text(pickle.dumps(event_data)) != event.event_data:
            event.event_data = db.Text(pickle.dumps(event_data))

            # Don't push update to avoid pushing twice (if both changed)
            AddOrUpdateEvent(event_data,
                             event=cal_event,
                             push_update=False)

          # Push all updates to calendar event
          # TODO(dhermes) see if possible to manage this from feed
          GCAL.Update(cal_event)

          # After all possible changes to the Event instance have occurred
          event.put()


class MainHandler(webapp.RequestHandler):

  @login_required
  def get(self):
    """This handler is responsible for fetching an initial OAuth
    request token and redirecting the user to the approval page."""

    # gauranteed to be a user since login_required
    current_user = users.get_current_user()
    template_vals = {'id': current_user.email()}

    # TODO(dhermes) look up UserCal and populate subscriptions/frequency
    path = os.path.join(os.path.dirname(__file__), 'templates', 'index.html')
    self.response.out.write(template.render(path, template_vals))

  def post(self):
#     frequency = self.request.get('frequency', None)
#     if frequency in ['three-hrs', 'six-hrs', 'half-day',
#                      'day', 'two-day', 'week']:
#       # split week in 56 3 hour windows, and assign the entire
#       # list based on these windows
#       now = datetime.utcnow()
      
#       a = 1

    # TODO(dhermes): Add whitelist on adding for accepted providers
    # TODO(dhermes): Improve to take account for scheme (webcal not real scheme)
    link = self.request.get('calendar-link', '').strip()
    link = 'http:%s' % urlparse.urlparse(link).path

    # TODO(dhermes): make sure user is logged in
    current_user = users.get_current_user()

    user_cal = UserCal.get_by_key_name(current_user.user_id())
    if user_cal is None:
      user_cal = UserCal(key_name=current_user.user_id(),
                         owner=current_user, calendars=[link])
      user_cal.put()
    elif link not in user_cal.calendars:
      user_cal.calendars.append(link)
      user_cal.put()

    UpdateSubcription(link, current_user)

    self.redirect('/')


class OwnershipVerifyHandler(webapp.RequestHandler):
  """Handles / as well as redirects for login required"""

  def get(self):
    path = os.path.join(os.path.dirname(__file__),
                        'googlef7560eebc24762bb.html')
    self.response.out.write(template.render(path, {}))


class Throw404(webapp.RequestHandler):
  """Catches all non-specified (404) requests"""

  def get(self):
    self.error(404)
    path = os.path.join(os.path.dirname(__file__), 'templates', '404.html')
    self.response.out.write(template.render(path, {}))


application = webapp.WSGIApplication([
  ('/', MainHandler),
  ('/googlef7560eebc24762bb.html', OwnershipVerifyHandler),
  ('/.*', Throw404),
  ], debug=True)


if __name__ == '__main__':
  run_wsgi_app(application)

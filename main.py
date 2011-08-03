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

# Create an instance of the DocsService to make API calls
GCAL = gdata.calendar.client.CalendarClient(source='persistent-cal')


def FormatTime(time_value):
  # Currently only expecting datetime.datetime or datetime.date

  # strftime('%Y-%m-%dT%H:%M:%S.000Z')
  # works with both date and datetime instances
  time_parse = '%Y-%m-%d'
  if type(time_value) == datetime:
    # Default is UTC/GMT
    time_parse += 'T%H:%M:%S.000Z'
  return time_value.strftime(time_parse)


def ProcessEventID(event_id, current_user):
  # currently, only supporting TripIt
  if not event_id.startswith('item-'):
    return '%s;user:%s' % (event_id, current_user.user_id())
  else:
    return event_id


def ParseEvent(event):
  # Assumes event is type icalendar.cal.Event
  
  # all events have a UID, and almost all begin with 'item-';
  # those that don't are an away event for the entire trip
  uid = unicode(event.get('uid'))
  event_data = {'when:from': event.get('dtstart').dt,
                'when:to': event.get('dtend').dt,
                'summary': unicode(event.get('summary')),
                'location': unicode(event.get('location')),
                'description': unicode(event.get('description'))}
  return uid, event_data


def ParseEditLink(link, current_user):
  # Reference:
  # http://code.google.com/apis/calendar/data/2.0/reference.html#Event_feeds
  link_params = urlparse.urlparse(link).path.split('/')
  if not link.startswith('https://www.google.com/calendar/feeds/') or len(link_params) != 7:
    raise Exception('Bad edit link %s' % link)

  # Due to first half of the boolean expr. we know link_params starts with
  # ['', 'calendar', 'feeds', ...
  if link_params[3] == 'default':
    link_params[3] = current_user.email()

  return 'https://www.google.com' + '/'.join(link_params)


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

# # WITNESS:
# # DAN
# (u'4754cd75888cac4a53c7cf003980e195b46dc9fd@tripit.com',
#  {'description': u'Daniel Hermes is in San Diego, CA from Sep 1 to Sep 6, 2011\nView and/or edit details in TripIt : http://www.tripit.com/trip/show/id/18643091\nTripIt - organize your travel at http://www.tripit.com\n',
#   'location': u'San Diego, CA',
#   'summary': u'Car/Hotel Reservation',
#   'when:from': datetime.date(2011, 9, 1),
#   'when:to': datetime.date(2011, 9, 7)})

# # SHARONA
# (u'4754cd75888cac4a53c7cf003980e195b46dc9fd@tripit.com',
#  {'description': u'Sharona Franko is in San Diego, CA from Sep 1 to Sep 6, 2011\nView and/or edit details in TripIt : http://www.tripit.com/trip/show/id/18643091\nTripIt - organize your travel at http://www.tripit.com\n',
#   'location': u'San Diego, CA',
#   'summary': u'Car/Hotel Reservation',
#   'when:from': datetime.date(2011, 9, 1),
#   'when:to': datetime.date(2011, 9, 7)})

def AddOrUpdateEvent(event_data, calendar_client, event=None, push_update=True):
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
      calendar_client.Update(event)
    return event
  else: 
    # Who
    who_add = gdata.calendar.data.EventWho(email=event_data['email'])
    event.who.append(who_add)

    # TODO(dhermes): reconsider ownership (follows the below)
    # Insert to calendar, thus making the owner of the client
    # the owner/author of the event. All subsequent people to add
    # said event will not be able to edit the event for everyone
    # else but the author will be
    new_event = calendar_client.InsertEvent(event)
    return new_event


def UpdateSubcription(link, calendar_client, current_user):
  current_user_id = current_user.user_id()

  # Make sure we are in correct calendar
  access_token_key = 'access_token_%s' % current_user_id
  # TODO(dhermes): this might not load/exist
  calendar_client.auth_token = gdata.gauth.ae_load(access_token_key)

  feed = urlopen(link)
  ical = Calendar.from_string(feed.read())
  feed.close()

  for component in ical.walk():
    # TODO(dhermes) add calendar name to event data
    if component.name == "VEVENT":
      uid, event_data = ParseEvent(component)
      uid = ProcessEventID(uid, current_user)
      event = Event.get_by_key_name(uid)
      if event is None:
        # Create new event in user's calendar
        # (leaving the uri argument creates new)
        event_data['email'] = current_user.email()
        cal_event = AddOrUpdateEvent(event_data, calendar_client)

        # Add event to datastore for tracking
        # TODO(dhermes): consider adding a universal private calendar for all
        #                events and granting a new user access upon signup
        gcal_edit = ParseEditLink(cal_event.get_edit_link().href, current_user)
        event = Event(key_name=uid,
                      owners=[current_user_id],  # id is string
                      event_data=db.Text(pickle.dumps(event_data)),
                      gcal_edit=gcal_edit)
        event.put()
      else:
        # We need to make changes for new event data or a new owner
        if (current_user_id not in event.owners or
            db.Text(pickle.dumps(event_data)) != event.event_data):
          # Grab GCal event to edit
          cal_event = calendar_client.GetEventEntry(uri=event.gcal_edit)

          # Update owners
          if current_user_id not in event.owners:
            event.owners.append(current_user_id)  # id is string

            # add existing event to current_user's calendar
            who_add = gdata.calendar.data.EventWho(email=current_user.email())
            cal_event.who.append(who_add)

          # Update existing event
          if db.Text(pickle.dumps(event_data)) != event.event_data:
            event.event_data = db.Text(pickle.dumps(event_data))

            # Don't push update to avoid pushing twice (if both changed)
            AddOrUpdateEvent(event_data, calendar_client,
                             event=cal_event, push_update=False)

          # Push all updates to calendar event
          calendar_client.Update(cal_event)

          # After all possible changes to the Event instance have occurred
          event.put()


class MainHandler(webapp.RequestHandler):

  @login_required
  def get(self):
    """This handler is responsible for fetching an initial OAuth
    request token and redirecting the user to the approval page."""

    # gauranteed to be a user since login_required
    current_user = users.get_current_user()

    # First determine if we have been granted access for the user
    access_token_key = 'access_token_%s' % current_user.user_id()
    access_token = gdata.gauth.ae_load(access_token_key)
    granted = (access_token is not None)
    template_vals = {'id': current_user.email(), 'granted': granted}
    if not granted:
      request_token_key = 'request_token_%s' % current_user.user_id()
      scopes = ['https://www.google.com/calendar/feeds/']
      oauth_callback = 'http://%s/verify' % self.request.host
      request_token = GCAL.get_oauth_token(scopes, oauth_callback,
                                           CONSUMER_KEY, CONSUMER_SECRET)

      # Persist this token in the datastore.
      gdata.gauth.ae_save(request_token, request_token_key)

      # Generate the authorization URL.
      template_vals['link'] = request_token.generate_authorization_url()

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

    UpdateSubcription(link, GCAL, current_user)

    self.redirect('/')


class RequestTokenCallback(webapp.RequestHandler):

  @login_required
  def get(self):
    """When the user grants access, they are redirected back to this
    handler where their authorized request token is exchanged for a
    long-lived access token."""

    current_user = users.get_current_user()

    # Check if access_token exists
    access_token_key = 'access_token_%s' % current_user.user_id()
    access_token = gdata.gauth.ae_load(access_token_key)
    # If not, upgrade the request_token to an access_token
    if access_token is None:
      request_token_key = 'request_token_%s' % current_user.user_id()
      # TODO(dhermes): might not exist
      request_token = gdata.gauth.ae_load(request_token_key)
      gdata.gauth.authorize_request_token(request_token, self.request.uri)
      auth_token_key = 'auth_token_%s' % current_user.user_id()
      gdata.gauth.ae_save(request_token, auth_token_key)

      # We can now upgrade our authorized token to a long-lived access token
      GCAL.auth_token = GCAL.get_access_token(request_token)
      gdata.gauth.ae_save(request_token, access_token_key)

    path = os.path.join(os.path.dirname(__file__), 'templates', 'verify.html')
    self.response.out.write(template.render(path, {}))


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
  ('/verify', RequestTokenCallback),
  ('/googlef7560eebc24762bb.html', OwnershipVerifyHandler),
  ('/.*', Throw404),
  ], debug=True)


if __name__ == '__main__':
  run_wsgi_app(application)

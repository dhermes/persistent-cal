# General libraries
import os
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


def parse_event(event):
  # all events have a UID, and almost all begin with 'item-';
  # those that don't are an away event for the entire trip
  uid = unicode(event.get('uid'))
  event_data = {'when:from': event.get('dtstart').dt,
                'when:to': event.get('dtend').dt,
                'summary': unicode(event.get('summary')),
                'location': unicode(event.get('location')),
                'description': unicode(event.get('description'))}
  return uid, event_data


class MainHandler(webapp.RequestHandler):

  @login_required
  def get(self):
    """This handler is responsible for fetching an initial OAuth
    request token and redirecting the user to the approval page."""

    # gauranteed to be a user since login_required
    current_user = users.get_current_user()

    # First determine if we have been granted access for the user
    access_token_key = 'access_token_%s' % current_user.user_id()
    request_token = gdata.gauth.ae_load(access_token_key)
    granted = (request_token is not None)    
    template_vals = {'granted': granted}
    if not granted:
      request_token_key = 'request_token_%s' % current_user.user_id()
      scopes = ['https://www.google.com/calendar/feeds/']
      oauth_callback = 'http://%s/verify' % self.request.host
      consumer_key = CONSUMER_KEY
      consumer_secret = CONSUMER_SECRET
      request_token = GCAL.get_oauth_token(scopes, oauth_callback,
                                           consumer_key, consumer_secret)

      # Persist this token in the datastore.
      gdata.gauth.ae_save(request_token, request_token_key)

      # Generate the authorization URL.
      template_vals['link'] = request_token.generate_authorization_url()

    path = os.path.join(os.path.dirname(__file__), 'templates', 'index.html')
    self.response.out.write(template.render(path, template_vals))

  @login_required
  def post(self):
    link = self.request.get('calendar-link')

    # gauranteed to be a user since login_required
    current_user = users.get_current_user()
    user_cal = UserCal(owner=current_user, calendars=[link])
    user_cal.put()

    link = 'http:%s ' % urlparse.urlparse(link).path  # Bad assumption, TODO
    feed = urlopen(link)
    ical = Calendar.from_string(feed.read())
    feed.close()

    for component in ical.walk():
      if component.name == "VEVENT":
        uid, event_data = parse_event(component)
        event_match = Event.get_by_key_name(uid)
        # SELECT * FROM Token WHERE __key__ = Key('Token', key)
        if event_match.count() == 0:
          # Make sure we are in correct calendar
          auth_token_key = 'auth_token_%s' % current_user.user_id()
          GCAL.auth_token = gdata.gauth.ae_load(auth_token_key)  # TODO, this will break
          
          # Create event in users calendar
          event = gdata.calendar.data.CalendarEventEntry()
          event.title = atom.data.Title(text=event_data['summary'])
          event.content = atom.data.Content(text=event_data['description'])
          event.where.append(gdata.calendar.data.CalendarWhere(
              value=event_data['location']))
          # strftime('%Y-%m-%dT%H:%M:%S.000Z')
          # works with both date and datetime
          start_time = event_data['when:from']. \
                       strftime('%Y-%m-%dT%H:%M:%S.000Z')
          end_time = event_data['when:to']. \
                     strftime('%Y-%m-%dT%H:%M:%S.000Z')
          event.when.append(gdata.calendar.data.When(start=start_time,
                                                     end=end_time))
          new_event = GCAL.InsertEvent(event)

          # Add event to datastore for tracking
          event_instance = Event(key_name=uid,
                                 owners=[current_user.user_id()],
                                 event_data=db.Text(pickle.dumps(event_data)),
                                 event_gcal_id=new_event.id.text)
          event_instance.put()
        elif event_match.count() == 1:
          event_match = event_match.get()

    self.redirect('/')


class RequestTokenCallback(webapp.RequestHandler):

  @login_required
  def get(self):
    """When the user grants access, they are redirected back to this
    handler where their authorized request token is exchanged for a
    long-lived access token."""

    current_user = users.get_current_user()

    # Remember the token that we stashed? Let's get it back from
    # datastore now and adds information to allow it to become an
    # access token.
    access_token_key = 'access_token_%s' % current_user.user_id()
    request_token = gdata.gauth.ae_load(access_token_key)
    if request_token is None:
      request_token_key = 'request_token_%s' % current_user.user_id()
      request_token = gdata.gauth.ae_load(request_token_key)
      gdata.gauth.authorize_request_token(request_token, self.request.uri)
      auth_token_key = 'auth_token_%s' % current_user.user_id()
      gdata.gauth.ae_save(request_token, auth_token_key)

      # We can now upgrade our authorized token to a long-lived
      # access token by associating it with the GCAL client, and
      # calling the get_access_token method.
      GCAL.auth_token = GCAL.get_access_token(request_token)

      # Note that we want to keep the access token around, as it
      # will be valid for all API calls in the future until a user
      # revokes our access. For example, it could be populated later
      # from reading from the datastore or some other persistence
      # mechanism.
      gdata.gauth.ae_save(request_token, access_token_key)

    # Always moving on
    message = '<a href="%s">Let\'s get started</a>'
    self.response.out.write(message % '/started')


class VerifyHandler(webapp.RequestHandler):
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


# event = gdata.calendar.data.CalendarEventEntry()
# event.title = atom.data.Title(text=title)
# event.content = atom.data.Content(text=content)
# where='On the courts'
# event.where.append(gdata.calendar.data.CalendarWhere(value=where))
# %Y-%m-%dT%H:%M:%S.000Z
# start_time = time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime())
# .... returns '2011-07-31T23:44:54.000Z' (in UTC)
# whereas my things have format
# 2011-08-01T08:00:00.000-07:00
# event.when.append(gdata.calendar.data.When(start=start_time, end=end_time))
# new_event = calendar_client.InsertEvent(event)

application = webapp.WSGIApplication([
  ###############
  ### EXAMPLE ###
  ###############
  ('/', MainHandler),
  ('/verify', RequestTokenCallback),
  ###############
  ###############
  ('/googlef7560eebc24762bb.html', VerifyHandler),
  ('/.*', Throw404),
  ], debug=True)


def main():
    run_wsgi_app(application)


if __name__ == '__main__':
    main()

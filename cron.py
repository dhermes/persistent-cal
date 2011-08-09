# General libraries
from datetime import datetime

# Third-party libraries
import gdata.gauth
import gdata.calendar.client

# App engine specific libraries
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app

# App specific libraries
from library import ConvertToInterval
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


class MainHandler(webapp.RequestHandler):

  def get(self):
    """Updates every three hours."""
    now = ConvertToInterval(datetime.utcnow())

    all_users = UserCal.all()
    for user in all_users:
      if now in user.update_intervals:
        for link in user.calendars:
          UpdateSubscription(link, user.owner, GCAL)


application = webapp.WSGIApplication([
  ('/cron', MainHandler),
  ], debug=True)


if __name__ == '__main__':
  run_wsgi_app(application)

from icalendar import Calendar
from urllib2 import urlopen
from urllib2 import urlparse

link = ('webcal://www.tripit.com/feed/ical/private/'
        '3F43994D-4591D1AA4C63B1472D8D5D0E9568E5A8/tripit.ics')
link = 'http:%s ' % urlparse.urlparse(link).path

feed = urlopen(link)
cal_feed = feed.read()
feed.close()

ical = Calendar.from_string(cal_feed)
name = ical.get('X-WR-CALNAME').__str__()
for component in ical.walk():
  if component.name == "VEVENT":
    print component.get('summary')
    print component.get('dtstart')
    print component.get('dtend')
    print component.get('dtstamp')

# VEVENT(
#   {'DTSTAMP': <icalendar.prop.vDDDTypes instance at 0x10152aab8>,
#    'UID': vText(u'item-a218099f87f84bb18818b575b345d9333d4260aa@tripit.com'),
#    'SUMMARY': vText(u'WN1999 LAS to SFO'),
#    'LOCATION': vText(u'Las Vegas (LAS)'),
#    'DTEND': <icalendar.prop.vDDDTypes instance at 0x10152ab00>,
#    'DTSTART': <icalendar.prop.vDDDTypes instance at 0x10152ab48>,
#    'GEO': <icalendar.prop.vGeo instance at 0x10152ab90>,
#    'DESCRIPTION': vText(u'View and/or edit details in TripIt : '
#                         'http://www.tripit.com/trip/show/id/18587799\n \n'
#                         '[Flight] 10/1/2011 Southwest Airlines(WN) #1999 dep '
#                         'LAS 6:05pm PDT arr SFO 7:35pm PDT; Daniel Jerome '
#                         'Hermes, Sharona Haya Franko; conf #W95N92 \nBooked '
#                         'on http://www.southwest.com/; '
#                         'http://www.southwest.com/; 1-800-435-9792 \n \n \n\n'
#                         'TripIt - organize your travel at http://www.tripit.com'
#                         )})


# TODO: incorporate default reminders (or ask),
#       daylight savings

# component.get('dtend').dt = datetime.datetime object

# GCal -> iCal correspondences:
# - title -> summary
# - when:from -> dstart
# - when:to -> dend
# - where -> location
# - calendar -> None
# - description -> description
# - reminders -> None
# Note: geo gives but who knows what for lat and lng

ff.name == 'VCALENDAR'
title = ff.get('X-WR-CALNAME').__str__()

# component.uid should be no repeat - vText(u'item-a218099f87f84bb18818b575b345d9333d4260aa@tripit.com')

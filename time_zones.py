from datetime import datetime
from datetime import timedelta
from datetime import tzinfo

ZERO = timedelta(0)
HOUR = timedelta(hours=1)

class UTC(tzinfo):
  """UTC"""

  def utcoffset(self, dt):
    return ZERO

  def tzname(self, dt):
    return "UTC"

  def dst(self, dt):
    return ZERO

# utc = UTC()

class USTimeZone(tzinfo):

  def __init__(self, hours, reprname, stdname, dstname):
    self.stdoffset = timedelta(hours=hours)
    self.reprname = reprname
    self.stdname = stdname
    self.dstname = dstname

  def __repr__(self):
    return self.reprname

  def tzname(self, dt):
    if self.dst(dt):
      return self.dstname
    else:
      return self.stdname

  def utcoffset(self, dt):
    return self.stdoffset + self.dst(dt)

  def dst(self, dt):
    if dt is None or dt.tzinfo is None:
      # An exception may be sensible here, in one or both cases.
      # It depends on how you want to treat them.  The default
      # fromutc() implementation (called by the default astimezone()
      # implementation) passes a datetime with dt.tzinfo is self.
      return ZERO
    assert dt.tzinfo is self

    # Find start and end times for US DST. For years before 1967, return
    # ZERO for no DST.
    if 2006 < dt.year:
      dststart, dstend = DSTSTART_2007, DSTEND_2007
    elif 1986 < dt.year < 2007:
      dststart, dstend = DSTSTART_1987_2006, DSTEND_1987_2006
    elif 1966 < dt.year < 1987:
      dststart, dstend = DSTSTART_1967_1986, DSTEND_1967_1986
    else:
      return ZERO

    start = first_sunday_on_or_after(dststart.replace(year=dt.year))
    end = first_sunday_on_or_after(dstend.replace(year=dt.year))

    # Can't compare naive to aware objects, so strip the timezone from
    # dt first.
    if start <= dt.replace(tzinfo=None) < end:
      return HOUR
    else:
      return ZERO

Eastern  = USTimeZone(-5, "Eastern",  "EST", "EDT")
Central  = USTimeZone(-6, "Central",  "CST", "CDT")
Mountain = USTimeZone(-7, "Mountain", "MST", "MDT")
Pacific  = USTimeZone(-8, "Pacific",  "PST", "PDT")

#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Planet aggregator library.

This package is a library for developing web sites or software that
aggregate RSS, CDF and Atom feeds taken from elsewhere into a single,
combined feed.
"""

__version__ = "1.0~pre1"
__authors__ = [ "Scott James Remnant <scott@netsplit.com>",
                "Jeff Waugh <jdub@perkypants.org>" ]
__license__ = "Python"


# Modules available without separate import
import cache
import feedparser
import htmltmpl
try:
    import logging
except:
    import compat_logging as logging

# Limit the effect of "from planet import *"
__all__ = ("cache", "feedparser", "htmltmpl", "logging",
           "Planet", "Channel", "NewsItem")


import os
import md5
import time
import dbhash


# Version information (for generator headers)
VERSION = ("Planet/%s +http://www.planetplanet.org" % __version__)

# Default User-Agent header to send when retreiving feeds
USER_AGENT = VERSION + " " + feedparser.USER_AGENT

# Default cache directory
CACHE_DIRECTORY = "cache"

# Default number of items to display from a new feed
NEW_FEED_ITEMS = 2

# Useful common date/time formats
TIMEFMT_ISO = "%Y-%m-%dT%H:%M:%S+00:00"
TIMEFMT_822 = "%a, %d %b %Y %H:%M:%S +0000"


# Log instance to use here
log = logging.getLogger("planet")


class Planet:
    """A set of channels.

    This class represents a set of channels for which the items will
    be aggregated together into one combined feed.

    Properties:
        user_agent      User-Agent header to fetch feeds with.
        cache_directory Directory to store cached channels in.
        new_feed_items  Number of items to display from a new feed.
    """
    def __init__(self):
        self._channels = []

        self.user_agent = USER_AGENT
        self.cache_directory = CACHE_DIRECTORY
        self.new_feed_items = NEW_FEED_ITEMS

    def channels(self, hidden=0, sorted=1):
        """Return the list of channels."""
        channels = []
        for channel in self._channels:
            if hidden or not channel.has_key("hidden"):
                channels.append((channel.name, channel))

        if sorted:
            channels.sort()

        return [ c[-1] for c in channels ]

    def subscribe(self, channel):
        """Subscribe the planet to the channel."""
        self._channels.append(channel)

    def unsubscribe(self, channel):
        """Unsubscribe the planet from the channel."""
        self._channels.remove(channel)

    def items(self, hidden=0, sorted=1, max_items=0, max_days=0):
        """Return an optionally filtered list of items in the channel.

        The filters are applied in the following order:

        If hidden is true then items in hidden channels and hidden items
        will be returned.

        If sorted is true then the item list will be sorted with the newest
        first.

        If max_items is non-zero then this number of items, at most, will
        be returned.

        If max_days is non-zero then any items older than the newest by
        this number of days won't be returned.  Requires sorted=1 to work.


        The sharp-eyed will note that this looks a little strange code-wise,
        it turns out that Python gets *really* slow if we try to sort the
        actual items themselves.  Also we use mktime here, but it's ok
        because we discard the numbers and just need them to be relatively
        consistent between each other.
        """
        items = []
        for channel in self.channels(hidden=hidden, sorted=0):
            for item in channel._items.values():
                if hidden or not item.has_key("hidden"):
                    items.append((time.mktime(item.date), item.order, item))

        # Sort the list
        if sorted:
            items.sort()
            items.reverse()

        # Apply max_items filter
        if len(items) and max_items:
            items = items[:max_items]

        # Apply max_days filter
        if len(items) and max_days:
            max_count = 0
            max_time = items[0][0] - max_days * 84600
            for item in items:
                if item[0] > max_time:
                    max_count += 1
                else:
                    items = items[:max_count]
                    break

        return [ i[-1] for i in items ]

class Channel(cache.CachedInfo):
    """A list of news items.

    This class represents a list of news items taken from the feed of
    a website or other source.

    Properties:
        url             URL of the feed.
        url_etag        E-Tag of the feed URL.
        url_modified    Last modified time of the feed URL.
        hidden          Channel should be hidden (True if exists).
        name            Name of the feed owner, or feed title.
        next_order      Next order number to be assigned to NewsItem

        updated         Correct UTC-Normalised update time of the feed.
        last_updated    Correct UTC-Normalised time the feed was last updated.

        id              An identifier the feed claims is unique (*).
        title           One-line title (*).
        link            Link to the original format feed (*).
        tagline         Short description of the feed (*).
        info            Longer description of the feed (*).

        modified        Date the feed claims to have been modified (*).

        author          Name of the author (*).
        publisher       Name of the publisher (*).
        generator       Name of the feed generator (*).
        category        Category name (*).
        copyright       Copyright information for humans to read (*).
        license         Link to the licence for the content (*).
        docs            Link to the specification of the feed format (*).
        language        Primary language (*).
        errorreportsto  E-Mail address to send error reports to (*).

        image_url       URL of an associated image (*).
        image_link      Link to go with the associated image (*).
        image_title     Alternative text of the associated image (*).
        image_width     Width of the associated image (*).
        image_height    Height of the associated image (*).

    Properties marked (*) will only be present if the original feed
    contained them.  Note that the optional 'modified' date field is simply
    a claim made by the item and parsed from the information given, 'updated'
    (and 'last_updated') are far more reliable sources of information.

    Some feeds may define additional properties to those above.
    """
    IGNORE_KEYS = ("links", "contributors", "textinput", "cloud", "categories",
                   "url", "url_etag", "url_modified")

    def __init__(self, planet, url):
        if not os.path.isdir(planet.cache_directory):
            os.makedirs(planet.cache_directory)
        cache_filename = cache.filename(planet.cache_directory, url)
        cache_file = dbhash.open(cache_filename, "c", 0666)

        cache.CachedInfo.__init__(self, cache_file, url, root=1)

        self._items = {}
        self._planet = planet
        self._expired = []
        self.url = url
        self.url_etag = None
        self.url_modified = None
        self.name = None
        self.updated = None
        self.last_updated = None
        self.next_order = "0"
        self.cache_read()
        self.cache_read_entries()

    def has_item(self, id_):
        """Check whether the item exists in the channel."""
        return self._items.has_key(id_)

    def get_item(self, id_):
        """Return the item from the channel."""
        return self._items[id_]

    # Special methods
    __contains__ = has_item

    def items(self, hidden=0, sorted=0):
        """Return the item list."""
        items = []
        for item in self._items.values():
            if hidden or not item.has_key("hidden"):
                items.append((time.mktime(item.date), item.order, item))

        if sorted:
            items.sort()
            items.reverse()

        return [ i[-1] for i in items ]

    def __iter__(self):
        """Iterate the sorted item list."""
        return iter(self.items(sorted=1))

    def cache_read_entries(self):
        """Read entry information from the cache."""
        keys = self._cache.keys()
        for key in keys:
            if key.find(" ") != -1: continue
            if self.has_key(key): continue

            item = NewsItem(self, key)
            self._items[key] = item

    def cache_write(self, sync=1):
        """Write channel and item information to the cache."""
        for item in self._items.values():
            item.cache_write(sync=0)
        for item in self._expired:
            item.cache_clear(sync=0)
        cache.CachedInfo.cache_write(self, sync)

        self._expired = []

    def update(self):
        """Download the feed to refresh the information.

        This does the actual work of pulling down the feed and if it changes
        updates the cached information about the feed and entries within it.
        """
        info = feedparser.parse(self.url,
                                etag=self.url_etag, modified=self.url_modified,
                                agent=self._planet.user_agent)
        if not info.has_key("status"):
            log.info("Updating feed <%s>", self.url)
        elif info.status == 301 or info.status == 302:
            log.warning("Feed has moved from <%s> to <%s>", self.url, info.url)
            os.link(cache.filename(self._planet.cache_directory, self.url),
                    cache.filename(self._planet.cache_directory, info.url))
            self.url = info.url
        elif info.status == 304:
            log.info("Feed <%s> unchanged", self.url)
            return
        elif info.status >= 400:
            log.error("Error %d while updating feed <%s>",
                      info.status, self.url)
            return
        else:
            log.info("Updating feed <%s>", self.url)

        self.url_etag = info.has_key("etag") and info.etag or None
        self.url_modified = info.has_key("modified") and info.modified or None
        if self.url_etag is not None:
            log.debug("E-Tag: %s", self.url_etag)
        if self.url_modified is not None:
            log.debug("Last Modified: %s",
                      time.strftime(TIMEFMT_ISO, self.url_modified))

        self.update_info(info.feed)
        self.update_entries(info.entries)
        self.cache_write()

    def update_info(self, feed):
        """Update information from the feed.

        This reads the feed information supplied by feedparser and updates
        the cached information about the feed.  These are the various
        potentially interesting properties that you might care about.
        """
        for key in feed.keys():
            if key in self.IGNORE_KEYS or key + "_parsed" in self.IGNORE_KEYS:
                # Ignored fields
                pass
            elif feed.has_key(key + "_parsed"):
                # Ignore unparsed date fields
                pass
            elif key.endswith("_detail"):
                # Ignore detail fields
                pass
            elif key.endswith("_parsed"):
                # Date fields
                if feed[key] is not None:
                    self.set_as_date(key[:-len("_parsed")], feed[key])
            elif key == "image":
                # Image field: save all the information
                if feed[key].has_key("url"):
                    self.set_as_string(key + "_url", feed[key].url)
                if feed[key].has_key("link"):
                    self.set_as_string(key + "_link", feed[key].link)
                if feed[key].has_key("title"):
                    self.set_as_string(key + "_title", feed[key].title)
                if feed[key].has_key("width"):
                    self.set_as_string(key + "_width", str(feed[key].width))
                if feed[key].has_key("height"):
                    self.set_as_string(key + "_height", str(feed[key].height))
            else:
                # String fields
                try:
                    self.set_as_string(key, feed[key])
                except KeyboardInterrupt:
                    raise
                except:
                    log.exception("Ignored '%s' of <%s>, unknown format",
                                  key, self.url)

    def update_entries(self, entries):
        """Update entries from the feed.

        This reads the entries supplied by feedparser and updates the
        cached information about them.  It's at this point we update
        the 'updated' timestamp and keep the old one in 'last_updated',
        these provide boundaries for acceptable entry times.

        If this is the first time a feed has been updated then most of the
        items will be marked as hidden, according to Planet.new_feed_items.

        If the feed does not contain items which, according to the sort order,
        should be there; those items are assumed to have been expired from
        the feed or replaced and are removed from the cache.
        """
        if not len(entries):
            return

        self.last_updated = self.updated
        self.updated = time.gmtime()

        new_items = []
        feed_items = []
        for entry in entries:
            # Try really hard to find some kind of unique identifier
            if entry.has_key("id"):
                entry_id = cache.utf8(entry.id)
            elif entry.has_key("link"):
                entry_id = cache.utf8(entry.link)
            elif entry.has_key("title"):
                entry_id = (self.url + "/"
                            + md5.new(cache.utf8(entry.title)).hexdigest())
            elif entry.has_key("summary"):
                entry_id = (self.url + "/"
                            + md5.new(cache.utf8(entry.summary)).hexdigest())
            else:
                log.error("Unable to find or generate id, entry ignored")
                continue

            # Create the item if necessary and update
            if self.has_item(entry_id):
                item = self._items[entry_id]
            else:
                item = NewsItem(self, entry_id)
                self._items[entry_id] = item
                new_items.append(item)
            item.update(entry)
            feed_items.append(entry_id)

            # Hide excess items the first time through
            if self.last_updated is None  and self._planet.new_feed_items \
                   and len(feed_items) > self._planet.new_feed_items:
                item.hidden = "yes"
                log.debug("Marked <%s> as hidden (new feed)", entry_id)

        # Assign order numbers in reverse
        new_items.reverse()
        for item in new_items:
            item.order = self.next_order = str(int(self.next_order) + 1)

        # Check for expired or replaced items
        feed_count = len(feed_items)
        log.debug("Items in Feed: %d", feed_count)
        for item in self.items(sorted=1):
            if feed_count < 1:
                break
            elif item.id in feed_items:
                feed_count -= 1
            else:
                del(self._items[item.id])
                self._expired.append(item)
                log.debug("Removed expired or replaced item <%s>", item.id)

    def get_name(self, key):
        """Return the key containing the name."""
        for key in ("name", "title"):
            if self.has_key(key) and self.key_type(key) != self.NULL:
                return self.get_as_string(key)

        return ""

class NewsItem(cache.CachedInfo):
    """An item of news.

    This class represents a single item of news on a channel.  They're
    created by members of the Channel class and accessible through it.

    Properties:
        id              Channel-unique identifier for this item.
        date            Corrected UTC-Normalised update time, for sorting.
        order           Order in which items on the same date can be sorted.
        hidden          Item should be hidden (True if exists).

        title           One-line title (*).
        link            Link to the original format text (*).
        summary         Short first-page summary (*).
        content         Full HTML content.

        modified        Date the item claims to have been modified (*).
        issued          Date the item claims to have been issued (*).
        created         Date the item claims to have been created (*).
        expired         Date the item claims to expire (*).

        author          Name of the author (*).
        publisher       Name of the publisher (*).
        category        Category name (*).
        comments        Link to a page to enter comments (*).
        license         Link to the licence for the content (*).
        source_name     Name of the original source of this item (*).
        source_link     Link to the original source of this item (*).

    Properties marked (*) will only be present if the original feed
    contained them.  Note that the various optional date fields are
    simply claims made by the item and parsed from the information
    given, 'date' is a far more reliable source of information.

    Some feeds may define additional properties to those above.
    """
    IGNORE_KEYS = ("categories", "contributors", "enclosures", "links",
                   "guidislink", "date")

    def __init__(self, channel, id_):
        cache.CachedInfo.__init__(self, channel._cache, id_)

        self._channel = channel
        self.id = id_
        self.date = None
        self.order = None
        self.content = None
        self.cache_read()

    def update(self, entry):
        """Update the item from the feedparser entry given."""
        for key in entry.keys():
            if key in self.IGNORE_KEYS or key + "_parsed" in self.IGNORE_KEYS:
                # Ignored fields
                pass
            elif entry.has_key(key + "_parsed"):
                # Ignore unparsed date fields
                pass
            elif key.endswith("_detail"):
                # Ignore detail fields
                pass
            elif key.endswith("_parsed"):
                # Date fields
                if entry[key] is not None:
                    self.set_as_date(key[:-len("_parsed")], entry[key])
            elif key == "source":
                # Source field: save both url and value
                if entry[key].has_key("value"):
                    self.set_as_string(key + "_name", entry[key].value)
                if entry[key].has_key("url"):
                    self.set_as_string(key + "_link", entry[key].url)
            elif key == "content":
                # Content field: concatenate the values
                value = ""
                for item in entry[key]:
                    value += cache.utf8(item.value)
                self.set_as_string(key, value)
            else:
                # String fields
                try:
                    self.set_as_string(key, entry[key])
                except KeyboardInterrupt:
                    raise
                except:
                    log.exception("Ignored '%s' of <%s>, unknown format",
                                  key, self.id)

        # Generate the date field if we need to
        self.get_date("date")

    def get_date(self, key):
        """Get (or update) the date key.

        We check whether the date the entry claims to have been changed is
        since we last updated this feed and when we pulled the feed off the
        site.

        If it is then it's probably not bogus, and we'll sort accordingly.

        If it isn't then we bound it appropriately, this ensures that
        entries appear in posting sequence but don't overlap entries
        added in previous updates and don't creep into the next one.
        """
        if self.has_key(key) and self.key_type(key) != self.NULL:
            return self.get_as_date(key)

        for other_key in ("modified", "issued", "created"):
            if self.has_key(other_key):
                date = self.get_as_date(other_key)
                break
        else:
            date = None

        if date is not None:
            if date > self._channel.updated:
                date = self._channel.updated
            elif date < self._channel.last_updated:
                date = self._channel.updated
        else:
            date = self._channel.updated

        self.set_as_date(key, date)
        return date

    def get_content(self, key):
        """Return the key containing the content."""
        for key in ("content", "tagline", "summary"):
            if self.has_key(key) and self.key_type(key) != self.NULL:
                return self.get_as_string(key)

        return ""

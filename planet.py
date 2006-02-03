#!/usr/bin/env python
"""The Planet aggregator.

A flexible and easy-to-use aggregator for generating websites.

Visit http://www.planetplanet.org/ for more information and to download
the latest version.

Requires Python 2.1, recommends 2.3.
"""

__authors__ = [ "Scott James Remnant <scott@netsplit.com>",
                "Jeff Waugh <jdub@perkypants.org>" ]
__license__ = "Python"


import os
import sys
import time
import locale

import planet

from ConfigParser import ConfigParser


# Default configuration file path
CONFIG_FILE = "config.ini"

# Defaults for the [Planet] config section
PLANET_NAME = "Unconfigured Planet"
PLANET_LINK = "Unconfigured Planet"
OWNER_NAME  = "Anonymous Coward"
OWNER_EMAIL = ""
LOG_LEVEL   = "WARNING"

# Default template file list
TEMPLATE_FILES = "examples/basic/planet.html.tmpl"

# Defaults for the template file config sections
OUTPUT_DIR      = "output"
DATE_FORMAT     = "%B %d, %Y %I:%M %p"
NEW_DATE_FORMAT = "%B %d, %Y"
ENCODING        = "utf-8"
ITEMS_PER_PAGE  = 60
DAYS_PER_PAGE   = 0


def config_get(config, section, option, default=None, raw=0, vars=None):
    """Get a value from the configuration, with a default."""
    if config.has_option(section, option):
        return config.get(section, option, raw=raw, vars=None)
    else:
        return default

def tmpl_config_get(config, template, option, default=None, raw=0, vars=None):
    """Get a template value from the configuration, with a default."""
    if config.has_option(template, option):
        return config.get(template, option, raw=raw, vars=None)
    elif config.has_option("Planet", option):
        return config.get("Planet", option, raw=raw, vars=None)
    else:
        return default

def template_info(item, date_format):
    """Produce a dictionary of template information."""
    info = {}
    for key in item.keys():
        if item.key_type(key) == item.DATE:
            date = item.get_as_date(key)
            info[key] = time.strftime(date_format, date)
            info[key + "_iso"] = time.strftime(planet.TIMEFMT_ISO, date)
            info[key + "_822"] = time.strftime(planet.TIMEFMT_822, date)
        else:
            info[key] = item[key]
    return info

def main():
    config_file = CONFIG_FILE
    offline = 0
    verbose = 0

    for arg in sys.argv[1:]:
        if arg == "-h" or arg == "--help":
            print "Usage: planet [options] [CONFIGFILE]"
            print
            print "Options:"
            print " -v, --verbose       DEBUG level logging during update"
            print " -o, --offline       Update the Planet from the cache only"
            print " -h, --help          Display this help message and exit"
            print
            sys.exit(0)
        elif arg == "-v" or arg == "--verbose":
            verbose = 1
        elif arg == "-o" or arg == "--offline":
            offline = 1
        elif arg.startswith("-"):
            print >>sys.stderr, "Unknown option:", arg
            sys.exit(1)
        else:
            config_file = arg

    # Read the configuration file
    config = ConfigParser()
    config.read(config_file)
    if not config.has_section("Planet"):
        print >>sys.stderr, "Configuration missing [Planet] section."
        sys.exit(1)

    # Read the [Planet] config section
    planet_name = config_get(config, "Planet", "name",        PLANET_NAME)
    planet_link = config_get(config, "Planet", "link",        PLANET_LINK)
    owner_name  = config_get(config, "Planet", "owner_name",  OWNER_NAME)
    owner_email = config_get(config, "Planet", "owner_email", OWNER_EMAIL)
    if verbose:
        log_level = "DEBUG"
    else:
        log_level  = config_get(config, "Planet", "log_level", LOG_LEVEL)
    template_files = config_get(config, "Planet", "template_files",
                                TEMPLATE_FILES).split(" ")

    # Define locale
    if config.has_option("Planet", "locale"):
        locale.setlocale(locale.LC_ALL, config.get("Planet", "locale"))

    # Activate logging
    planet.logging.basicConfig()
    planet.logging.getLogger().setLevel(planet.logging.getLevelName(log_level))
    log = planet.logging.getLogger("planet.runner")

    # Create a planet
    log.info("Loading cached data")
    my_planet = planet.Planet()
    if config.has_option("Planet", "cache_directory"):
        my_planet.cache_directory = config.get("Planet", "cache_directory")
    if config.has_option("Planet", "new_feed_items"):
        my_planet.new_feed_items  = int(config.get("Planet", "new_feed_items"))
    my_planet.user_agent = "%s +%s %s" % (planet_name, planet_link,
                                          my_planet.user_agent)
    if config.has_option("Planet", "filter"):
        my_planet.filter = config.get("Planet", "filter")

    # The other configuration blocks are channels to subscribe to
    for feed_url in config.sections():
        if feed_url == "Planet" or feed_url in template_files:
            continue

        # Create a channel, configure it and subscribe it
        channel = planet.Channel(my_planet, feed_url)
        for option in config.options(feed_url):
            value = config.get(feed_url, option)
            channel.set_as_string(option, value, cached=0)
        my_planet.subscribe(channel)

        # Update it
        try:
            if not offline:
                channel.update()
        except KeyboardInterrupt:
            raise
        except:
            log.exception("Update of <%s> failed", feed_url)

    # Go-go-gadget-template
    manager = planet.htmltmpl.TemplateManager()
    for template_file in template_files:
        log.info("Processing template %s", template_file)
        template = manager.prepare(template_file)

        # Read the configuration
        output_dir = tmpl_config_get(config, template_file,
                                     "output_dir", OUTPUT_DIR)
        date_format = tmpl_config_get(config, template_file,
                                      "date_format", DATE_FORMAT, raw=1)
        new_date_format = tmpl_config_get(config, template_file,
                                          "new_date_format", NEW_DATE_FORMAT,
                                          raw=1)
        encoding = tmpl_config_get(config, template_file, "encoding", ENCODING)
        items_per_page = int(tmpl_config_get(config, template_file,
                                             "items_per_page", ITEMS_PER_PAGE))
        days_per_page = int(tmpl_config_get(config, template_file,
                                            "days_per_page", DAYS_PER_PAGE))

        # We treat each template individually
        base = os.path.splitext(os.path.basename(template_file))[0]
        url = os.path.join(planet_link, base)
        output_file = os.path.join(output_dir, base)

        # Gather channel information
        channels = {}
        channels_list = []
        for channel in my_planet.channels(hidden=1):
            channels[channel] = template_info(channel, date_format)
            channels_list.append(channels[channel])

        # Gather item information
        items_list = []
        prev_date = []
        prev_channel = None
        for newsitem in my_planet.items(max_items=items_per_page,
                                        max_days=days_per_page):
            item_info = template_info(newsitem, date_format)
            chan_info = channels[newsitem._channel]
            for k, v in chan_info.items():
                item_info["channel_" + k] = v

            # Check for the start of a new day
            if prev_date[:3] != newsitem.date[:3]:
                prev_date = newsitem.date
                item_info["new_date"] = time.strftime(new_date_format,
                                                      newsitem.date)

            # Check for the start of a new channel
            if item_info.has_key("new_date") \
                   or prev_channel != newsitem._channel:
                prev_channel = newsitem._channel
                item_info["new_channel"] = newsitem._channel.url

            items_list.append(item_info)

        # Process the template
        tp = planet.htmltmpl.TemplateProcessor(html_escape=0)
        tp.set("Items", items_list)
        tp.set("Channels", channels_list)

        # Generic information
        tp.set("generator",   planet.VERSION)
        tp.set("name",        planet_name)
        tp.set("link",        planet_link)
        tp.set("owner_name",  owner_name)
        tp.set("owner_email", owner_email)
        tp.set("url",         url)

        # Update time
        date = time.gmtime()
        tp.set("date",        time.strftime(date_format, date))
        tp.set("date_iso",    time.strftime(planet.TIMEFMT_ISO, date))
        tp.set("date_822",    time.strftime(planet.TIMEFMT_822, date))

        try:
            log.info("Writing %s", output_file)
            output_fd = open(output_file, "w")
            if encoding.lower() in ("utf-8", "utf8"):
                # UTF-8 output is the default because we use that internally
                output_fd.write(tp.process(template))
            elif encoding.lower() in ("xml", "html", "sgml"):
                # Magic for Python 2.3 users
                output = tp.process(template).decode("utf-8")
                output_fd.write(output.encode("ascii", "xmlcharrefreplace"))
            else:
                # Must be a "known" encoding
                output = tp.process(template).decode("utf-8")
                output_fd.write(output.encode(encoding, "replace"))
            output_fd.close()
        except KeyboardInterrupt:
            raise
        except:
            log.exception("Write of %s failed", output_file)

if __name__ == "__main__":
    main()


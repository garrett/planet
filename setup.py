#!/usr/bin/env python
"""The Planet aggregator."""

__authors__ = [ "Scott James Remnant <scott@netsplit.com>",
                "Jeff Waugh <jdub@perkypants.org>" ]
__license__ = "Python"


from distutils.core import setup

from planet import __version__ as planet_ver

setup(name="planet",
      version=planet_ver,
      packages=["planet", "planet.compat_logging"],
      scripts=["planet.py", "planet-cache.py"],
      description="The Planet aggregator",
      url="http://www.planetplanet.org/",
      author="Scott James Remnant and Jeff Waugh",
      author_email="devel@lists.planetplanet.org",
      )

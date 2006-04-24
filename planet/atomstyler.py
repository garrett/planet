from xml.dom import minidom, Node
from urlparse import urlparse, urlunparse
from xml.parsers.expat import ExpatError
from htmlentitydefs import name2codepoint
import re

# select and apply an xml:base for this entry
class relativize:
  def __init__(self, parent):
    self.score = {}
    self.collect_and_tally(parent)
    self.base = self.select_optimal_base()
    if self.base:
      if not parent.hasAttribute('xml:base'):
        self.rebase(parent)
        parent.setAttribute('xml:base', self.base)

  # collect and tally href and src attributes
  def collect_and_tally(self,parent):
    uri = None
    if parent.hasAttribute('href'): uri=parent.getAttribute('href')
    if parent.hasAttribute('src'): uri=parent.getAttribute('src')

    if uri:
      parts=urlparse(uri)
      if parts[0].lower() == 'http':
        parts = (parts[1]+parts[2]).split('/')
        for i in range(1,len(parts)):
          base = tuple(parts[0:i])
          self.score[base] = self.score.get(base,0) + len(base)

    for node in parent.childNodes:
      if node.nodeType == Node.ELEMENT_NODE:
        self.collect_and_tally(node)
    
  # select the xml:base with the highest score
  def select_optimal_base(self):
    if not self.score: return None
    winner = max(self.score.values())
    for key in self.score.keys():
      if self.score[key] == winner:
        if winner == len(key): return None
        return urlunparse(('http', key[0], '/'.join(key[1:]), '', '', '')) + '/'
    
  # rewrite href and src attributes using this base
  def rebase(self,parent):
    uri = None
    if parent.hasAttribute('href'): uri=parent.getAttribute('href')
    if parent.hasAttribute('src'): uri=parent.getAttribute('src')
    if uri and uri.startswith(self.base):
      uri = uri[len(self.base):] or '.'
      if parent.hasAttribute('href'): uri=parent.setAttribute('href', uri)
      if parent.hasAttribute('src'): uri=parent.setAttribute('src', uri)

    for node in parent.childNodes:
      if node.nodeType == Node.ELEMENT_NODE:
        self.rebase(node)

# convert type="html" to type="plain" or type="xhtml" as appropriate
def retype(parent):
  for node in parent.childNodes:
    if node.nodeType == Node.ELEMENT_NODE:
      if node.hasAttribute('type') and node.getAttribute('type') == 'html':
        if len(node.childNodes)==1:

          # replace html entity defs with utf-8
          chunks=re.split('&(\w+);', node.childNodes[0].nodeValue)
          for i in range(1,len(chunks),2):
             if chunks[i] in ['amp', 'lt', 'gt', 'apos', 'quot']:
               chunks[i] ='&' + chunks[i] +';'
             elif chunks[i] in name2codepoint:
               chunks[i]=unichr(name2codepoint[chunks[i]])
             else:
               chunks[i]='&' + chunks[i] + ';'
          text = u"".join(chunks)

          try:
            # see if the resulting text is a well-formed XML fragment
            div = '<div xmlns="http://www.w3.org/1999/xhtml">%s</div>'
            data = minidom.parseString((div % text.encode('utf-8')))

            if text.find('<') < 0:
              # plain text
              node.removeAttribute('type')
              text = data.documentElement.childNodes[0].nodeValue
              node.childNodes[0].replaceWholeText(text)

            elif len(text) > 80:
              # xhtml
              node.setAttribute('type', 'xhtml')
              node.removeChild(node.childNodes[0])
              node.appendChild(data.documentElement)
              if node.nodeName == 'content':
                relativize(node.parentNode)

          except ExpatError:
            # leave as html
            pass

      else:
        # recurse
        retype(node)

if __name__ == '__main__':

  # run styler on each file mention on the command line
  import sys
  for feed in sys.argv[1:]:
    doc = minidom.parse(feed)
    doc.normalize()
    retype(doc.documentElement)
    open(feed,'w').write(doc.toxml('utf-8'))

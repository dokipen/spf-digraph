"""
A tool to create a digraph of spf lookups.
Copyright (C) 2015 Robert Corsaro

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
from dns.resolver import query
from dns.exception import DNSException
import json
import logging

logger = logging.getLogger('spf-digraph')


def debug(*args, **kwargs):
    logger.debug(*args, **kwargs)


def find(f, itr, default=None):
    """
    find first node that matches predicate
    """
    for x in itr:
        if f(x):
            return x
    return default


class Node(object):
    """
    Node for resolve message tree
    """

    def __init__(self, name):
        self.name = name
        self.children_names = set()
        self.children = []

    def add_child(self, name):
        if name not in self.children_names:
            node = Node(name)
            self.children.append(node)
            self.children_names.add(node.name)
            return node
        else:
            return find(lambda x: x.name == name, self.children)

    def __unicode__(self):
        return "{} -> ({})".format(self.name, ', '.join(map(unicode,
                                                            self.children)))

    def __str__(self):
        return self.__unicode__()

    def to_obj(self):
        return {
            'name': self.name,
            'children': list(self.children_names),
        }


class TreeBuilder(object):
    """
    Builds Node tree from resolve messages
    """

    def __init__(self):
        self.stack = []
        self.resolver = Resolver()

    def build(self, domain):
        """
        Returns a tree of the spf lookups
        """
        tree = None
        for typ, name in self.resolver(domain):
            debug("-> ({}, {})".format(typ, name))
            if typ == 'enter':
                if len(self.stack):
                    node = self.stack[-1].add_child(name)
                else:
                    node = Node(name)
                self.stack.append(node)
            elif typ == 'exit':
                tree = Tree(self.stack.pop())
        return tree


class Resolver(object):
    """
    Resolve spf records
    """

    @classmethod
    def is_include(cls, record):
        """
        is an include spf record?
        """
        return record.startswith('include:')

    @classmethod
    def to_text(cls, x):
        """
        Convert dns record to text
        """
        return x.to_text()

    @classmethod
    def is_spf(cls, x):
        """
        Is the TXT record an spf record?
        """
        return x.strip('"').startswith('v=spf1')

    def __call__(self, domain, visited=None):
        """
        queries spf records on domain recursively, sending messages to caller
        as it enters and exits each DNS record.
        """
        if not visited:
            visited = set()

        if domain in visited:
            return
        visited.add(domain)

        yield 'enter', domain

        try:
            res = map(self.to_text, query(domain, "TXT"))
            terms = find(self.is_spf, res, '').split()
            for record in filter(self.is_include, terms):
                name = record.split(':')[1]
                for typ, name in self(name, visited):
                    yield typ, name
        except DNSException:
            logger.exception("Failed DNS lookup on {}".format(domain))

        yield 'exit', domain


class Tree(object):
    """
    Tree of nodes
    """

    def __init__(self, head):
        self.head = head

    def bigrams(self, node=None):
        """
        generates bigrams for each relationship in the graph
        """
        if not node:
            node = self.head

        if len(node.children):
            for n in node.children:
                for bigram in self.bigrams(n):
                    yield bigram
                yield node.name, n.name

    def __unicode__(self):
        return unicode(self.head)

    def __str__(self):
        return self.__unicode__()

    def each_node(self, visited=None, node=None):
        if not visited:
            visited = set()
        if not node:
            node = self.head
        if node.name in visited:
            return

        visited.add(node.name)
        yield node
        if len(node.children):
            for n in node.children:
                for r in self.each_node(visited, n):
                    yield r

    def to_json(self):
        return json.dumps([n.to_obj() for n in self.each_node()])

def digraph(domain):
    print 'digraph G {'
    for a, b in set(TreeBuilder().build(domain).bigrams()):
        print '    "{}" -> "{}"'.format(a, b)
    print '}'

def as_json(domain):
    print TreeBuilder().build(domain).to_json()

if __name__ == '__main__':
    import sys
    import os

    if os.environ.get("DEBUG", 'false').lower() not in ('0', 'false'):
        logging.basicConfig(level=logging.DEBUG)

    if len(sys.argv) != 2:
        "ERROR: Takes one argument that is domain name"
        sys.exit(1)

    (os.environ.get("FORMAT") == 'json' and as_json or digraph)(sys.argv[1])

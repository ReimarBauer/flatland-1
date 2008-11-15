from __future__ import absolute_import

import itertools
import logging
from genshi import Markup, Namespace, Stream, QName
from genshi.core import START, TEXT
from genshi.template.eval import Expression

import flatland
from flatland.util import Maybe
from . taglistener import TagListener, default_start


__all__ = 'flatland_filter',

log = logging.getLogger('flatland.out.genshi')

NAMESPACE  = Namespace('http://ns.discorporate.us/flatland/genshi')

# filter attributes
F_BIND     = NAMESPACE['bind']

# HTML attribues
H_CHECKED = QName('checked')
H_FOR = QName('for')
H_ID = QName('id')
H_NAME = QName('name')
H_SELECTED = QName('selected')
H_TABINDEX = QName('tabindex')
H_VALUE = QName('value')

MAYBE = ('auto',)
YES   = ('1', 'true', 't', 'on', 'yes')
NO    = ('0', 'false', 'nil', 'off', 'no')

CTX_CUR_TABINDEX      = 'auto-tabindex_value'
CTX_FMT_DOMID         = 'auto-domid_format'




def flatland_filter(stream, context):
    """flatland_filter(stream, context) -> stream

    Filter a stream through FlatlandFilter

    """
    return Stream(FlatlandFilter()(stream, context))




class ToggledAttribute(object):
    toggle_attribute = None
    toggle_default = False
    toggle_context_key = None

    attribute = None
    auto_tags = ()

    def pop_toggle(self, attrs, context):
        attrs, proceed = self.pop_attribute(
            attrs, self.toggle_attribute, 'auto', parse_trool)
        forced = proceed is True
        if proceed is Maybe:
            proceed = parse_trool(context.get(self.toggle_context_key, 'auto'))
            if proceed is Maybe:
                proceed = self.toggle_default
        return attrs, proceed, forced

    def pop_attribute(self, attrs, name, default=None, transform=None):
        value = attrs.get(name, default)
        if transform:
            value = transform(value)
        return (attrs - name), value


class NameToggle(ToggledAttribute):
    toggle_default = True
    toggle_attribute = NAMESPACE['auto-name']
    toggle_context_key = 'auto-name'

    attribute = H_NAME
    auto_tags = set(('input', 'button', 'select', 'textarea', 'form'))

    def apply_to(self, tag, attrs, context, node):
        attrs, proceed, forced = self.pop_toggle(attrs, context)

        if not proceed:
            return attrs

        # Abort on unbound or anonymous nodes
        if node is None or node.name is None:
            return attrs

        current = attrs.get(self.attribute, None)
        if forced or current is None and tag.localname in self.auto_tags:
            attrs |= ((self.attribute, node.flattened_name()),)
        return attrs


class ValueToggle(ToggledAttribute):
    toggle_default = True
    toggle_attribute = NAMESPACE['auto-value']
    toggle_context_key = 'auto-value'

    attribute = H_VALUE
    auto_tags = set(('input', 'select', 'textarea', 'button'))

    apply_child = ('textarea',)
    apply_mixed = ()

    def apply_to(self, tag, attrs, stream, context, node):
        attrs, proceed, forced = self.pop_toggle(attrs, context)

        if not proceed:
            return stream, attrs

        # Abort on unbound nodes.
        if node is None:
            return stream, attrs

        if not forced and tag.localname not in self.auto_tags:
            return stream, attrs

        # VALUE_CHILD (e.g. <textarea>) always replaces the stream with
        # the node's string value.
        if tag.localname in self.apply_child:
            stream = self.set_stream_value(stream, node.u)

        elif tag.localname == 'select':
            stream = self.set_select(forced, attrs, stream, node)

        elif tag.localname in self.apply_mixed:
            stream, attrs = self.set_mixed_value(forced, attrs, stream, node)

        elif tag.localname == 'input':
            attrs = self.set_input(forced, attrs, node)

        else:
            attrs = self.set_simple_value(forced, attrs, node)

        return stream, attrs

    def set_stream_value(self, stream, text):
        stream = stream_is_empty(stream)
        if stream is None:
            return Stream([(TEXT, text, (None, -1, -1))])
        else:
            return stream

    def set_simple_value(self, override, attrs, node):
        current = attrs.get(H_VALUE)
        if current is None or override is True:
            attrs |= ((H_VALUE, node.u),)
        return attrs

    def set_mixed_value(self, override, attrs, stream, node):
        """
        For output nodes that may either take a 'value=""' or encode
        their value in nested content.  Node value will be passed
        along as unescaped markup if child nodes are generated!

        """
        if attrs.get(H_VALUE, None) is None:
            stream = self.set_stream_value(stream, Markup(node))
        else:
            attrs = self.set_simple_value(override, attrs, node)
        return stream, attrs

    def set_input(self, override, attrs, node):
        type = attrs.get('type', 'text').lower()

        if type in ('text', 'password', 'hidden', 'button', 'submit', 'reset'):
            attrs = self.set_simple_value(override, attrs, node)
        elif type in ('file', 'image'):
            if override is True:
                attrs = self.set_simple_value(override, attrs, node)
        elif type == 'checkbox':
            value = attrs.get(H_VALUE, None)
            if value is None and isinstance(node.schema, flatland.Boolean):
                value = node.schema.true
                attrs |= ((H_VALUE, value),)
            attrs = self.set_checked(attrs, node)
        elif type == 'radio':
            attrs = self.set_checked(attrs, node)
        else:
            if override is True:
                attrs = self.set_simple_value(override, attrs, node)
        return attrs

    def set_select(self, override, attrs, stream, node):
        return OptionToggler(node.u)(stream)

    def set_checked(self, attrs, node):
        value = attrs.get(H_VALUE, None)
        if value is None:
            return attrs
        if value == node.u:
            attrs |= ((H_CHECKED, 'checked'),)
        elif isinstance(node, flatland.schema.compound.Compound):
            attrs -= H_CHECKED
        else:
            for child in node.children:
                if value == child.u:
                    attrs |= ((H_CHECKED, 'checked'),)
                    break
            else:
                attrs -= H_CHECKED
        return attrs


class DomIDToggle(ToggledAttribute):
    toggle_attribute = NAMESPACE['auto-domid']
    toggle_context_key = 'auto-domid'

    attribute = H_ID
    auto_tags = set(('input', 'button', 'select', 'textarea'))

    def apply_to(self, tag, attrs, context, el):
        attrs, proceed, forced = self.pop_toggle(attrs, context)
        if not proceed:
            return attrs

        current = attrs.get(self.attribute, None)
        if forced or current is None and tag.localname in self.auto_tags:
            if el is not None:
                domid = self.id_for(el, context)
            else:
                domid = self.id_for_unbound(tag, attrs, context)
            attrs |= ((self.attribute, domid),)
        return attrs

    @classmethod
    def id_for(cls, el, context):
        fmt = context.get(CTX_FMT_DOMID, 'f_%s')
        return fmt % el.flattened_name()

    @classmethod
    def id_for_unbound(cls, tag, attrs, context):
        if tag in cls.auto_tags:
            name = attrs.get(H_NAME, None)
            if name is not None:
                fmt = context.get(CTX_FMT_DOMID, 'f_%s')
                return fmt % name
        return None


class ForToggle(ToggledAttribute):
    toggle_attribute = NAMESPACE['auto-for']
    # tied to ID generation
    toggle_context_key = 'auto-domid'

    attribute = H_FOR
    auto_tags = set(('label',))

    def apply_to(self, tag, attrs, context, node):
        attrs, proceed, forced = self.pop_toggle(attrs, context)
        if not proceed or node is None:
            return attrs

        current = attrs.get(self.attribute, None)
        if forced or current is None and tag.localname in self.auto_tags:
            attrs |= ((self.attribute, DomIDToggle.id_for(node, context)),)
        return attrs


class TabIndexToggle(ToggledAttribute):
    toggle_attribute = NAMESPACE['auto-tabindex']
    toggle_context_key = 'auto-tabindex'

    attribute = H_TABINDEX
    auto_tags = set(('input', 'button', 'select', 'textarea'))

    def apply_to(self, tag, attrs, context):
        attrs, proceed, forced = self.pop_toggle(attrs, context)
        if not proceed:
            return attrs

        tabindex = context.get(CTX_CUR_TABINDEX, 0)
        if tabindex == 0:
            return attrs

        current = attrs.get(self.attribute, None)
        if forced or current is None and tag.localname in self.auto_tags:
            attrs |= ((self.attribute, tabindex),)
            context[CTX_CUR_TABINDEX] = tabindex + 1
        return attrs


class OptionToggler(TagListener):
    __slots__ = ('value',)

    activated = ((H_SELECTED, 'selected'),)

    def __init__(self, value):
        self.value = value

    def inspect(self, event, context):
        kind, data, pos = event

        if kind is START and data[0].localname == 'option':
            return (default_start, self.end)
        else:
            return False

    def end(self, start, end, stream, context, history):
        kind, (tag, attrs), pos = start
        attrs -= H_SELECTED

        value = attrs.get(H_VALUE, None)
        if value is not None:
            if value == self.value:
                attrs |= ((H_SELECTED, 'selected'),)
        else:
            children = list(stream)
            value = ''
            for ck, cd, cp in children:
                if ck is TEXT: value += cd
            stream = Stream(children)

            if value.strip() == self.value.strip():
                attrs |= ((H_SELECTED, 'selected'),)

        start = kind, (tag, attrs), pos

        return start, end, stream


class DecoratedElementDirective(object):
    set_name = NameToggle().apply_to
    set_value = ValueToggle().apply_to
    set_domid = DomIDToggle().apply_to
    set_tabindex = TabIndexToggle().apply_to
    set_for = ForToggle().apply_to

    def start(self, event, context):
        kind, (tag, attrs), pos = event

        node = self.find_binding(tag, attrs, context)

        # Node-free transformations
        attrs = self.set_tabindex(tag, attrs, context)

        # Node-sensitive transformations
        attrs = self.set_domid(tag, attrs, context, node)

        return (kind, (tag, attrs), pos), dict(binding=node)

    def end(self, start, end, stream, context, history):
        kind, tag, pos = end
        start_kind, (start_tag, attrs), start_pos = start

        node = history.get('binding', None)
        attrs -= F_BIND

        # Set <... name=""> for bound nodes.
        attrs = self.set_name(tag, attrs, context, node)

        # Map <label for="..."> to bound tags.
        attrs = self.set_for(tag, attrs, context, node)

        # Set <... value=""> or tag-specific equivalent.
        stream, attrs = self.set_value(tag, attrs, stream, context, node)

        # Re-assemble the start event.
        start = (start_kind, (start_tag, attrs), start_pos)

        return start, end, stream

    def find_binding(self, tag, attributes, context):
        expr = attributes.get(F_BIND, None)
        if expr is None:
            return expr
        try:
            return Expression(expr).evaluate(context)
        except:
            log.error("Failed to parse binding %r" % expr,)
            raise


class ImmediateVarDirective(object):
    toggles = ('auto-tabindex', 'auto-domid', 'auto-for',
               'auto-name', 'auto-value')
    name = 'set'

    def start(self, event, context):
        kind, (tag, attrs), pos = event

        for toggle in self.toggles:
            val = attrs.get(toggle, None)
            if val is not None:
                context[toggle] = parse_trool(val)

        val = parse_int(attrs.get('tabindex', None))
        if val is not None:
            context[CTX_CUR_TABINDEX] = val

        val = attrs.get('domid-format', None)
        if val is not None:
            context[CTX_FMT_DOMID] = val

        return None, None

    def end(self, start, end, stream, context, history):
        return None, None, stream


class ScopedVarDirective(ImmediateVarDirective):
    name = 'with'

    def start(self, event, context):
        context.push({})
        return ImmediateVarDirective.start(self, event, context)

    def end(self, start, end, stream, context, history):
        context.pop()
        return ImmediateVarDirective.end(self, start, end, stream,
                                         context, history)


class FlatlandFilter(TagListener):
    """TODO: Document

    Binds template form elements to flatland data elements and
    automatically sets name, and value.  Manages DOM id generation,
    links <label> to matching elements and manages tabindex.

    """

    dir_with = ScopedVarDirective()
    dir_set  = ImmediateVarDirective()
    dir_el = DecoratedElementDirective()

    inspect_with = (dir_with.start, dir_with.end)
    inspect_set = (dir_set.start, dir_set.end)
    inspect_el = (dir_el.start, dir_el.end)

    def inspect(self, event, context):
        if event[0] is not START:
            return False

        kind, (tag, attributes), pos = event

        if tag in NAMESPACE:
            if tag.localname == self.dir_with.name:
                return self.inspect_with
            elif tag.localname == self.dir_set.name:
                return self.inspect_set
        else:
            for attr, value in attributes:
                if attr in NAMESPACE:
                    return self.inspect_el




def stream_is_empty(stream):
    stream, dupe = itertools.tee(stream)
    try:
        dupe.next()
    except StopIteration:
        return None
    else:
        return stream



def parse_bool(value, yes=YES, no=NO):
    if value is True or value is False or value is None:
        return value
    value = str(value).lower()
    if value in yes:
        return True
    if value in no:
        return False
    return None

def parse_trool(value):
    if value is True or value is False or value is Maybe:
        return value
    value = str(value).lower()
    if value in YES:
        return True
    if value in NO:
        return False
    if value in MAYBE:
        return Maybe
    return Maybe

def parse_int(text):
    if type(text) is int: return text
    try:
        return int(text)
    except:
        return None

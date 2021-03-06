# Copyright 2012 Thomas Jost
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software stributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.

import datetime

import dateutil.tz
import urwid

from bccc.client import ChannelError

# {{{ Channel box
class ChannelBox(urwid.widget.BoxWidget):
    _oldest_date = datetime.datetime.fromtimestamp(0, tz=dateutil.tz.tzlocal())

    def __init__(self, ui, channel):
        self.ui = ui
        self.channel = channel
        self.active = False
        self.unread_ids = set()
        user, domain = channel.jid.split("@", 1)

        # Domain: shorten my.long.domain.name into "mldn"
        domain = "".join([w[0] for w in domain.split(".")])

        # Init sub-widgets
        w = urwid.Text(user, wrap="clip")
        w = urwid.AttrMap(w, "channel user", "focused channel user")
        self.widget_user = w

        w = urwid.Text("@" + domain, wrap="clip")
        w = urwid.AttrMap(w, "channel domain", "focused channel domain")
        self.widget_domain = w

        w = urwid.Text("", align="right", wrap="clip")
        w = urwid.AttrMap(w, "channel notif", "focused channel notif")
        self.widget_notif = w

        w = urwid.Text("")
        w = urwid.AttrMap(w, "channel status", "focused channel status")
        self.widget_status = w

        # Channel configuration
        self.chan_title = ""
        self.chan_description = ""
        self.chan_creation = ""
        self.chan_type = ""

        # Channel callbacks
        _callbacks = {
            "cb_post":    ui.safe_callback(self.pubsub_posts_callback),
            "cb_retract": ui.safe_callback(self.pubsub_retract_callback),
            "cb_status":  ui.safe_callback(self.pubsub_status_callback),
            "cb_config":  ui.safe_callback(self.pubsub_config_clalback),
        }
        channel.set_callbacks(**_callbacks)

        # Request missing informations
        channel.pubsub_get_status()
        channel.pubsub_get_config()

        # Get most recent post/comment so we can sort by date
        self.most_recent_activity = self._oldest_date
        channel.pubsub_get_posts(max=1)

    # {{{ PubSub Callbacks
    def pubsub_posts_callback(self, atoms):
        # Find most recent atom
        recent_changed = False
        first_post_ever = (self.most_recent_activity == self._oldest_date)
        for atom in atoms:
            atom_pub = atom.published
            if atom_pub > self.most_recent_activity:
                self.most_recent_activity = atom_pub
                recent_changed = True

        # Tell the ChannelsList to sort channels again
        if recent_changed:
            self.ui.channels.sort_channels()

        if self.active:
            # Notify the content pane
            # TODO: more?
            self.ui.threads_list.add_new_items(atoms)
        elif not first_post_ever:
            # Update unread counter
            for a in atoms:
                self.unread_ids.add(a.id)
            nb_unread = len(self.unread_ids)
            if nb_unread > 0:
                self.widget_notif.original_widget.set_text(" [{}]".format(nb_unread))
                self._invalidate()

        self.ui.notify()

    def pubsub_retract_callback(self, item_ids):
        for id_ in item_ids:
            self.unread_ids.discard(id_)
        if self.active:
            self.ui.threads_list.remove_items(item_ids)
        self.ui.channels.sort_channels()
        # Don't notify the user...

    def pubsub_status_callback(self, atom):
        self.widget_status.original_widget.set_text(atom.content)
        self._invalidate()
        self.ui.notify()

    def pubsub_config_clalback(self, conf):
        self.set_config(conf)
        self.ui.notify()
    # }}}
    # {{{ Channel management
    def set_active(self, active):
        self.active = active
        if active:
            self.widget_user.set_attr_map({None: "active channel user"})
            self.widget_user.set_focus_map({None: "focused active channel user"})
            self.widget_domain.set_attr_map({None: "active channel domain"})
            self.widget_domain.set_focus_map({None: "focused active channel domain"})
            self.widget_notif.set_attr_map({None: "active channel notif"})
            self.widget_notif.set_focus_map({None: "focused active channel notif"})
            self.widget_status.set_attr_map({None: "active channel status"})
            self.widget_status.set_focus_map({None: "focused active channel status"})

            self.widget_notif.original_widget.set_text("")
            self.unread_ids.clear()

            self.display_config()
        else:
            self.widget_user.set_attr_map({None: "channel user"})
            self.widget_user.set_focus_map({None: "focused channel user"})
            self.widget_domain.set_attr_map({None: "channel domain"})
            self.widget_domain.set_focus_map({None: "focused channel domain"})
            self.widget_notif.set_attr_map({None: "channel notif"})
            self.widget_notif.set_focus_map({None: "focused channel notif"})
            self.widget_status.set_attr_map({None: "channel status"})
            self.widget_status.set_focus_map({None: "focused channel status"})

    def display_config(self):
        if self.active:
            self.ui.infobar_left.set_text("{} - {}".format(self.chan_title, self.chan_description))
            self.ui.infobar_right.set_text(self.channel.jid)

    def set_status(self, status):
        self.widget_status.original_widget.set_text(status)
        self._invalidate()

    def set_config(self, config):
        if "title" in config:
            self.chan_title = config["title"].strip()
        if "description" in config:
            self.chan_description = config["description"].strip()
        if "creation" in config:
            self.chan_creation = config["creation"].strftime("%x - %X")
        if "type" in config:
            self.chan_type = config["type"]
        self.display_config()
        self._invalidate()
    # }}}
    # {{{ Widget management
    def keypress(self, size, key):
        return key

    def rows(self, size, focus=False):
        return 1 + self.widget_status.rows(size, focus)

    def render(self, size, focus=False):
        maxcol = size[0]

        # First line: user, shortened domain, notif
        canv1, comb1 = None, None
        user_col, _ = self.widget_user.pack(focus=focus)
        if len(self.unread_ids) == 0:
            # No notification: just user + domain
            domain_col  = maxcol - user_col
            if domain_col > 0:
                canv_user = self.widget_user.render((user_col,), focus)
                canv_domain = self.widget_domain.render((domain_col,), focus)
                comb1 = [(canv_user,   None, True, user_col),
                         (canv_domain, None, True, domain_col)]
            else:
                canv1 = self.widget_user.render(size, focus)
        else:
            # There are notifications: now it's tricker
            notif_col, _ = self.widget_notif.pack(focus=focus)
            domain_col   = maxcol - user_col - notif_col
            if domain_col > 0:
                # Render everything!
                canv_user = self.widget_user.render((user_col,), focus)
                canv_domain = self.widget_domain.render((domain_col,), focus)
                canv_notif = self.widget_notif.render((notif_col,), focus)
                comb1 = [(canv_user,   None, True, user_col),
                         (canv_domain, None, True, domain_col),
                         (canv_notif,  None, True, notif_col)]
            else:
                # Only user and notif.
                user_col  = min(user_col, maxcol - notif_col)
                if user_col > 0:
                    # User + notif
                    canv_user = self.widget_user.render((user_col,), focus)
                    canv_notif = self.widget_notif.render((notif_col,), focus)
                    comb1 = [(canv_user,  None, True, user_col),
                             (canv_notif, None, True, notif_col)]
                else:
                    # Notif only
                    canv1 = self.widget_notif.render(size, focus)

        if comb1 is not None:
            canv1 = urwid.CanvasJoin(comb1)

        # Second (status)
        canv_status = self.widget_status.render(size, focus)

        # Combine lines
        combinelist = [(c, None, True) for c in (canv1, canv_status)]
        return urwid.CanvasCombine(combinelist)
    # }}}
# }}}
# {{{ Channels list
class ChannelsList(urwid.ListBox):
    """A list of channels"""

    def __init__(self, ui):
        self.ui = ui

        # Init ListBox with a SimpleListWalker
        self._channels = urwid.SimpleListWalker([])
        urwid.ListBox.__init__(self, self._channels)

        # No active channel for now
        self.active_channel = None

    def keypress(self, size, key):
        if key == "enter":
            focus_w, _ = self.get_focus()
            self.make_active(focus_w)
        else:
            return urwid.ListBox.keypress(self, size, key)

    def load_channels(self):
        # Request user channel
        user_chan = self.ui.client.get_channel()

        # Request user subscriptions
        chans = user_chan.get_subscriptions()

        # First empty the list
        del self._channels[:]

        # Then add each channel to it
        for chan in chans:
            w = ChannelBox(self.ui, chan)
            if chan.jid == self.ui.client.boundjid.bare:
                self._channels.insert(0, w)
                self.make_active(w)
            else:
                self._channels.append(w)

        # A nice divider :)
        self._channels.insert(1, urwid.Divider("─"))

        self.ui.refresh()

    def sort_channels(self):
        focus_w, _ = self.get_focus()
        sortable_chans = self._channels[2:]
        sortable_chans.sort(key=lambda cb: cb.most_recent_activity, reverse=True)
        self._channels[2:] = sortable_chans
        focus_pos = self._channels.index(focus_w)
        self.set_focus(focus_pos)
        self._invalidate()

    def reset(self):
        """Reset active channel. This is *violent*."""
        chan_box = self.active_channel
        idx = self._channels.index(chan_box)

        try:
            new_chan = self.ui.client.get_channel(chan_box.channel.jid, force_new=True)
        except ChannelError:
            return # TODO: display warning
        new_chan_box = ChannelBox(self.ui, new_chan)
        self._channels[idx] = new_chan_box
        self.make_active(new_chan_box)

    def make_active(self, chan):
        if self.active_channel is chan:
            return
        self.ui.status.set_text("Displaying channel {}...".format(chan.channel.jid))
        if self.active_channel is not None:
            self.active_channel.set_active(False)
        self.active_channel = chan
        chan.set_active(True)
        self.ui.threads_list.set_active_channel(chan.channel)

    def goto(self, jid=None):
        def _goto_channel(jid):
            jid = jid.strip()
            chan_idx = None

            # Is the jid in the channels list?
            for idx, chan in enumerate(self._channels):
                if type(chan) is ChannelBox and chan.channel.jid == jid:
                    chan_idx = idx
                    break

            # If it's not, add it
            if chan_idx is None:
                try:
                    channel = self.ui.client.get_channel(jid)
                except ChannelError:
                    return # TODO: display warning
                chan = ChannelBox(self.ui, channel)
                self._channels.append(chan)
                chan_idx = len(self._channels) - 1

            # Give focus and make channel active
            chan = self._channels[chan_idx]
            self.set_focus(chan_idx)
            self.make_active(chan)

        if jid is None:
            self.ui.status.ask("Go to channel: ", _goto_channel)
        else:
            _goto_channel(jid)
# }}}
# Local Variables:
# mode: python3
# End:

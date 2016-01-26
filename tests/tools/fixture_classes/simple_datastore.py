import json
import datetime
from collections import OrderedDict

import itertools
from em2.core.common import Components
from em2.core.datastore import DataStore, ConversationDataStore
from em2.core.exceptions import ConversationNotFound, ComponentNotFound


class UniversalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        if isinstance(obj, set):
            return sorted(obj)
        try:
            return super(UniversalEncoder, self).default(obj)
        except TypeError:
            return repr(obj)


class SimpleDataStore(DataStore):
    _conn_ctx = None

    def __init__(self):
        self.conversation_counter = itertools.count()
        self.data = {}
        super(SimpleDataStore, self).__init__()

    async def create_conversation(self, conn, **kwargs):
        id = next(self.conversation_counter)
        self.data[id] = dict(
            participant_counter=itertools.count(),  # special case with uses sequence id
            updates=[],
            locked=set(),
            expiration=None,
            **kwargs
        )
        return id

    @property
    def conv_data_store(self):
        return SimpleConversationDataStore

    def connection(self):
        # assert self._conn_ctx is None
        self._conn_ctx = VoidContextManager()
        return self._conn_ctx

    def reuse_connection(self):
        # assert self._conn_ctx is not None
        return self._conn_ctx

    def get_conv(self, conv_id):
        for v in self.data.values():
            if v['conv_id'] == conv_id:
                return v
        raise ConversationNotFound('conversation {} not found'.format(conv_id))

    def __repr__(self):
        return json.dumps(self.data, indent=2, sort_keys=True, cls=UniversalEncoder)


class VoidContextManager:
    async def __aenter__(self):
        pass

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class SimpleConversationDataStore(ConversationDataStore):
    def __init__(self, *args, **kwargs):
        super(SimpleConversationDataStore, self).__init__(*args, **kwargs)
        self.conv_obj = self.ds.get_conv(self.conv)

    async def get_core_properties(self):
        return {k: self.conv_obj[k] for k in self._core_property_keys}

    async def save_event(self, action, data):
        self.conv_obj['updates'].append({
            'actor': action.actor_id,
            'verb': action.verb,
            'component': action.component,
            'item': action.item,
            'data': data,
            'timestamp': action.timestamp,
        })

    async def set_published_id(self, new_timestamp, new_id):
        self.conv_obj.update(
            draft_conv_id=self.conv_obj['conv_id'],
            conv_id=new_id,
            timestamp=new_timestamp,
        )

    # Status

    async def set_status(self, status):
        self.conv_obj['status'] = status

    # Ref

    def set_ref(self, ref):
        self.conv_obj['ref'] = ref

    # Subject

    async def set_subject(self, subject):
        self.conv_obj['subject'] = subject

    # Component generic methods

    async def add_component(self, model, **kwargs):
        if model not in self.conv_obj:
            self.conv_obj[model] = OrderedDict()
        if model == Components.PARTICIPANTS:
            kwargs['id'] = next(self.conv_obj['participant_counter'])
        id = kwargs['id']
        self.conv_obj[model][id] = kwargs
        return id

    async def edit_component(self, model, item_id, **kwargs):
        item = self._get_conv_item(model, item_id)
        item.update(kwargs)

    async def delete_component(self, model, item_id):
        items = self._get_conv_items(model)
        try:
            del items[item_id]
        except KeyError:
            raise ComponentNotFound('{} with id = {} not found on conversation {}'.format(model, item_id, self.conv))

    async def lock_component(self, model, item_id):
        self._get_conv_item(model, item_id)
        self.conv_obj['locked'].add('{}:{}'.format(model, item_id))

    async def unlock_component(self, model, item_id):
        self.conv_obj['locked'].remove('{}:{}'.format(model, item_id))

    async def check_component_locked(self, model, item_id):
        return '{}:{}'.format(model, item_id) in self.conv_obj['locked']

    async def get_all_component_items(self, component):
        data = self.conv_obj.get(component, {})
        return list(data.values())

    # Messages

    async def get_message_meta(self, message_id):
        msgs = self.conv_obj.get(Components.MESSAGES, {})
        msg = msgs.get(message_id)
        if msg is None:
            raise ComponentNotFound('message {} not found in {}'.format(message_id, msgs.keys()))
        return {k: msg[k] for k in ('author', 'timestamp')}

    # Participants

    async def get_participant(self, participant_address):
        participants = self.conv_obj.get(Components.PARTICIPANTS, {})
        for v in participants.values():
            if v['address'] == participant_address:
                return v['id'], v['permissions']
        raise ComponentNotFound('participant {} not found'.format(participant_address))

    # internal methods

    def _get_conv_items(self, model):
        items = self.conv_obj.get(model)
        if items is None:
            raise ComponentNotFound('model "{}" not found on conversation {}'.format(model, self.conv))
        return items

    def _get_conv_item(self, model, item_id):
        items = self._get_conv_items(model)
        item = items.get(item_id)
        if item is None:
            raise ComponentNotFound('{} with id = {} not found on conversation {}'.format(model, item_id, self.conv))
        return item

    def __repr__(self):
        return self.__class__.__name__ + json.dumps(self.conv_obj, indent=2, sort_keys=True, cls=UniversalEncoder)

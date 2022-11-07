'''
Logging formatter to store in JSON easier.
'''
import logging
import json
import re
from datetime import date, datetime, time, timezone
import traceback, importlib

from typing import Any, Dict, Union, List, Tuple

from inspect import istraceback

from collections import OrderedDict


RESERVED_ATTRS: Tuple[str, ...] = (
    'args', 'asctime', 'created', 'exc_info', 'exc_text', 'filename',
    'funcName', 'levelname', 'levelno', 'lineno', 'module',
    'msecs', 'message', 'msg', 'name', 'pathname', 'process',
    'processName', 'relativeCreated', 'stack_info', 'thread', 'threadName')


def merge_record_extra(record: logging.LogRecord, target: Dict, reserved: Union[Dict, List]) -> Dict:
    for key, value in record.__dict__.items():
        # this allows to have numeric keys
        if (key not in reserved
            and not (hasattr(key, "startswith")
                     and key.startswith('_'))):
            target[key] = value
    return target


class JsonEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (date, datetime, time)):
            return self.format_datetime_obj(obj)

        elif istraceback(obj):
            return ''.join(traceback.format_tb(obj)).strip()

        elif type(obj) == Exception \
                or isinstance(obj, Exception) \
                or type(obj) == type:
            return str(obj)

        try:
            return super(JsonEncoder, self).default(obj)

        except TypeError:
            try:
                return str(obj)

            except Exception:
                return None

    def format_datetime_obj(self, obj):
        return obj.isoformat()


class JsonFormatter(logging.Formatter):
    def __init__(self, *args, **kwargs):
        self.json_default = self._str_to_fn(kwargs.pop("json_default", None))
        self.json_encoder = self._str_to_fn(kwargs.pop("json_encoder", None))
        self.json_serializer = self._str_to_fn(kwargs.pop("json_serializer", json.dumps))
        self.json_indent = kwargs.pop("json_indent", None)
        self.json_ensure_ascii = kwargs.pop("json_ensure_ascii", True)
        self.prefix = kwargs.pop("prefix", "")
        self.rename_fields = kwargs.pop("rename_fields", {})
        self.static_fields = kwargs.pop("static_fields", {})
        reserved_attrs = kwargs.pop("reserved_attrs", RESERVED_ATTRS)
        self.reserved_attrs = dict(zip(reserved_attrs, reserved_attrs))
        self.timestamp = kwargs.pop("timestamp", False)

        logging.Formatter.__init__(self, *args, **kwargs)
        if not self.json_encoder and not self.json_default:
            self.json_encoder = JsonEncoder

        self._required_fields = self.parse()
        self._skip_fields = dict(zip(self._required_fields,
                                     self._required_fields))
        self._skip_fields.update(self.reserved_attrs)

    def _str_to_fn(self, fn_as_str):
        if not isinstance(fn_as_str, str):
            return fn_as_str

        path, _, function = fn_as_str.rpartition('.')
        module = importlib.import_module(path)
        return getattr(module, function)

    def parse(self) -> List[str]:
        if isinstance(self._style, logging.StringTemplateStyle):
            formatter_style_pattern = re.compile(r'\$\{(.+?)\}', re.IGNORECASE)
        elif isinstance(self._style, logging.StrFormatStyle):
            formatter_style_pattern = re.compile(r'\{(.+?)\}', re.IGNORECASE)
        elif isinstance(self._style, logging.PercentStyle):
            formatter_style_pattern = re.compile(r'%\((.+?)\)', re.IGNORECASE)
        else:
            raise ValueError('Invalid format: %s' % self._fmt)

        if self._fmt:
            return formatter_style_pattern.findall(self._fmt)
        else:
            return []

    def add_fields(self, log_record: Dict[str, Any], record: logging.LogRecord, message_dict: Dict[str, Any]) -> None:
        for field in self._required_fields:
            if field in self.rename_fields:
                log_record[self.rename_fields[field]] = record.__dict__.get(field)
            else:
                log_record[field] = record.__dict__.get(field)
        log_record.update(self.static_fields)
        log_record.update(message_dict)
        merge_record_extra(record, log_record, reserved=self._skip_fields)

        if self.timestamp:
            key = self.timestamp if type(self.timestamp) == str else 'timestamp'
            log_record[key] = datetime.fromtimestamp(record.created, tz=timezone.utc)

    def process_log_record(self, log_record):
        return log_record

    def jsonify_log_record(self, log_record):
        return self.json_serializer(log_record,
                                    default=self.json_default,
                                    cls=self.json_encoder,
                                    indent=self.json_indent,
                                    ensure_ascii=self.json_ensure_ascii)

    def serialize_log_record(self, log_record: Dict[str, Any]) -> str:
        return "%s%s" % (self.prefix, self.jsonify_log_record(log_record))

    def format(self, record: logging.LogRecord) -> str:
        message_dict: Dict[str, Any] = {}
        if isinstance(record.msg, dict):
            message_dict = record.msg
            record.message = None
        else:
            record.message = record.getMessage()
        if "asctime" in self._required_fields:
            record.asctime = self.formatTime(record, self.datefmt)

        if record.exc_info and not message_dict.get('exc_info'):
            message_dict['exc_info'] = self.formatException(record.exc_info)
        if not message_dict.get('exc_info') and record.exc_text:
            message_dict['exc_info'] = record.exc_text
        try:
            if record.stack_info and not message_dict.get('stack_info'):
                message_dict['stack_info'] = self.formatStack(record.stack_info)
        except AttributeError:
            pass

        log_record: Dict[str, Any]
        log_record = OrderedDict()
        self.add_fields(log_record, record, message_dict)
        log_record = self.process_log_record(log_record)

        return self.serialize_log_record(log_record)

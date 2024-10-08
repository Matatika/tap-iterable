
#
# Module dependencies.
#

from datetime import datetime, timedelta
from singer import utils
from urllib.parse import urlencode
import backoff
import requests
import logging
import sys


logger = logging.getLogger()


""" Simple wrapper for Iterable. """
class Iterable(object):

  def __init__(self, api_key, start_date=None, api_window_in_days=30):
    self.api_key = api_key
    self.uri = "https://api.iterable.com/api/"
    self.api_window_in_days = int(api_window_in_days)
    self.MAX_BYTES = 10240
    self.CHUNK_SIZE = 512


  def _now(self):
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


  def _daterange(self, start_date, end_date):
    total_days = (utils.strptime_with_tz(end_date) - utils.strptime_with_tz(start_date)).days
    if total_days >= self.api_window_in_days:
      for n in range(int(total_days / self.api_window_in_days)):
        yield (utils.strptime_with_tz(start_date) + n * timedelta(int(self.api_window_in_days))).strftime("%Y-%m-%d %H:%M:%S")
    else:
      yield start_date


  def _get_end_datetime(self, startDateTime):
    endDateTime = utils.strptime_with_tz(startDateTime) + timedelta(self.api_window_in_days)
    return endDateTime.strftime("%Y-%m-%d %H:%M:%S")

  def fatal_code(e):
      return 401 == e.response.status_code

  def retry_handler(details):
    logger.info("Received %s -- sleeping for %s seconds",
                sys.exc_info()[1].response.status_code,
                details['wait'])

  # 
  # The actual `get` request.
  # 
  
  @backoff.on_exception(backoff.expo,
                        requests.exceptions.HTTPError,
                        on_backoff=retry_handler,
                        max_tries=10,
                        giveup=fatal_code)
  def _get(self, path, stream=True, **kwargs):
    uri = "{uri}{path}".format(uri=self.uri, path=path)
    
    # Add query params
    params = {}
    for key, value in kwargs.items():
      params[key] = value
    if params != {}:
      uri += "?{params}".format(params=urlencode(params))

    # Add Api_Key header
    headers = {"Api_Key": self.api_key}

    logger.info("GET request to {uri}".format(uri=uri))
    response = requests.get(uri, stream=stream, headers=headers)
    response.raise_for_status()
    return response

  #
  # The common `get` request.
  #
  
  def get(self, path, **kwargs):
    response = self._get(path, **kwargs)
    return response.json()

  #
  # Get custom user fields, used for generating `users` schema in `discover`.
  #

  def get_user_fields(self):
    return self.get("users/getFields")

  # 
  # Methods to retrieve data per stream/resource.
  # 

  def lists(self, column_name=None, bookmark=None):
    res = self.get("lists")
    for l in res["lists"]:
      yield l


  def list_users(self, column_name=None, bookmark=None):
    res = self.get("lists")
    for l in res["lists"]:
      kwargs = {
        "listId": l["id"]
      }
      users = self._get("lists/getUsers", **kwargs)
      for user in users:
        yield {
          "email": user,
          "listId": l["id"],
          "updatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z")
        }


  def campaigns(self, column_name=None, bookmark=None):
    res = self.get("campaigns")
    for c in res["campaigns"]:
      yield c


  def channels(self, column_name, bookmark):
    res = self.get("channels")
    for c in res["channels"]:
      yield c


  def message_types(self, column_name=None, bookmark=None):
    res = self.get("messageTypes")
    for m in res["messageTypes"]:
      yield m


  def templates(self, column_name, bookmark):
    template_types = [
      "Base",
      "Blast",
      "Triggered",
      "Workflow"
    ]
    message_mediums = [
      "Email",
      "Push",
      "InApp",
      "SMS"
    ]
    for template_type in template_types:
      for medium in message_mediums:
        res = self.get("templates", templateTypes=template_type, messageMedium=medium)
        for t in res["templates"]:
          yield t


  def metadata(self, column_name=None, bookmark=None):
    tables = self.get("metadata")
    for t in tables["results"]:
      keys = self.get("metadata/{table_name}".format(table_name=t["name"]))
      for k in keys["results"]:
        value = self.get("metadata/{table_name}/{key}".format(table_name=k["table"], key=k["key"]))
        yield value


  def get_data_export_generator(self, data_type_name, bookmark=None):
    now = self._now()
    kwargs = {}
    for start_date_time in self._daterange(bookmark, now):
      kwargs["startDateTime"] = start_date_time
      kwargs["endDateTime"] = self._get_end_datetime(startDateTime=start_date_time)
      def get_data():
        return self._get("export/data.json", dataTypeName=data_type_name, **kwargs)
      yield get_data







""" Helper functions for AppsCake. """
import json
import hashlib
import uuid
import os

from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import AccessTokenRefreshError
from oauth2client.client import OAuth2WebServerFlow
from oauth2client.file import Storage

from Crypto.Cipher import AES


# The scope used to request a refresh and access token.
GCE_SCOPE = 'https://www.googleapis.com/auth/compute'


# The URL users are redirected to after authorizing AppsCake to make
# GCE calls for them. It includes a query paramater named 'code' which
# is used to generate the OAuth2 dat file.
GCE_REDIRECT_URI = 'http://localhost:8080/oauth2_callback'


# The location on the file system where we store a users OAuth2 dat file.
# This is passed into the tools as an argument. 
GCE_OAUTH_FILE = '.data/.credentials-%s.dat'


def generate_keyname():
  """ Generates a random keyname to use for an AppScale deployment. 
  
  Returns:
    A string which is the name of the AppScale key. It starts with a 
      letter and has no dashes to be compliant with GCE network regexs.
  """
  return 'a' + str(uuid.uuid1()).replace('-','')


def delete_old_credentials(client_id):
  """ Deletes a users old GCE OAuth2 file, since it may be expired

  Args:
    client_id: A string that is a unique client id found in the secrets 
      which is used to uniquely identify each GCE account.
  """
  try:
    os.remove(GCE_OAUTH_FILE % client_id)
  except OSError:
    pass


def save_gce_credentials(client_id, code):
  """ Using the code from the OAuth2 callback, we generate the user's 
  OAuth2.dat file which is passed into the AppScale tools. 

  Args:
    client_id: A string that is a unique client id found in the secrets 
      which is used to uniquely identify each GCE account.
    code: A string that is the code returned to us in the OAuth2 callback.

  """
  client_id_hash = get_client_id_hash(client_id)
  client_secrets_location = '.data/.' + client_id_hash + '_secrets.json'
  flow = flow_from_clientsecrets(client_secrets_location, 
    scope=GCE_SCOPE, redirect_uri=GCE_REDIRECT_URI)
  credentials = flow.step2_exchange(code)
  storage = Storage(GCE_OAUTH_FILE % client_id)
  storage.put(credentials)


def get_client_id_from_client_secrets(client_secrets):
  """ Parses out the client id from the client_secrets JSON.
  
  Args:
    client_secrets: A string innput by the user on the web form whichcontains       various authorization parameters. 
  Returns:
    A string, the client id in the client_secrets.
  """
  json_data = json.loads(client_secrets)
  client_id = json_data['web']['client_id']
  return client_id


def get_decrypted_cookie_data(client_id, encrypted_data):
  """ Decrypts cookie data using an encryption string saved to the file system.
  
  Args:
    client_id: A string that is a unique client id found in the secrets
      which is used to uniquely identify each GCE account.
    encrypted_data: A string of the contents of the cookie which decrypts
      into a JSON string. 
  Returns:
    A json string with the users original form data.
  """
  client_id_hash = get_client_id_hash(client_id)
  file_name = '.data/.' + client_id_hash + '_crypt.txt'
  key_file = open(file_name, 'r')
  decrypt_key = str(key_file.read())
  key_file.close()
  decryptor = AES.new(decrypt_key, AES.MODE_CBC, 'This is an IV456')
  plaintext = decryptor.decrypt(encrypted_data)
  return plaintext.strip()
   

def get_encrypted_cookie_data(client_id, cookie_data):
  """ Gets an encrypted json string representing the users form data.
  
  Args:
    client_id: A string that is a unique client id found in the secrets
      which is used to uniquely identify each GCE account.
    cookie_data: A json string representing the users form data.
  Returns:
    A string that is the encryption of the cookie_data.
  """
  client_id_hash = get_client_id_hash(client_id)
  encryption_key = str(os.urandom(32))
  file_name = '.data/.' + client_id_hash + '_crypt.txt'
  key_file = open(file_name, 'w')
  key_file.write(encryption_key)
  key_file.close()
  crypt_obj = AES.new(encryption_key, AES.MODE_CBC, 'This is an IV456')
  cipher_text = crypt_obj.encrypt(pad_cookie_data(cookie_data))
  return cipher_text 

def get_form_data_as_json_string(email, password, max_nodes,
  deployment_type, instance_type, gce_image_name, project,
  client_secrets):
  """ 
  
  """
  data = [{ 'email':email, 'password':password, 'max_nodes':max_nodes,
    'deployment_type':deployment_type, 'instance_type':instance_type,
    'gce_image_name':gce_image_name, 'project':project,
    'client_secrets':client_secrets}]
  data_string = json.dumps(data)
  return data_string

def pad_cookie_data(cookie_data):
  data_length = cookie_data.__len__()
  padding_needed = 16 - (data_length % 16)
  return cookie_data.ljust(padding_needed + data_length)


def get_auth_server_uri(client_secrets):
  client_id = get_client_id_from_client_secrets(client_secrets)
  client_secrets_location = create_client_secrets_file(client_id,
    client_secrets)
  flow = flow_from_clientsecrets(client_secrets_location,
    scope=GCE_SCOPE, redirect_uri=GCE_REDIRECT_URI)
  uri = flow.step1_get_authorize_url()
  return str(uri)

def create_client_secrets_file(client_id, client_secrets):
  client_id_hash = get_client_id_hash(client_id)
  secrets_file_name = '.data/.' + client_id_hash + '_secrets.json'
  secrets_file = open(secrets_file_name, 'w')
  secrets_file.write(client_secrets)
  secrets_file.close()
  return secrets_file_name
   

def get_client_id_hash(client_id):
  h = hashlib.sha1()
  h.update(client_id)
  return str(h.hexdigest())

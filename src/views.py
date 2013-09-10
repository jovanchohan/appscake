""" Views for different pages in particular for starting and stopping AppScale.
"""
import logging
import os
import sys
import json

sys.path.append(os.path.join(os.path.dirname(__file__), "../"))
import helpers
import appscale_tools_thread
from forms import CommonFields
 
from django.http import HttpResponse
from django.http import HttpResponseServerError
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.utils import simplejson

from apiclient.discovery import build
from oauth2client.client import AccessTokenRefreshError
from oauth2client.client import OAuth2WebServerFlow
from oauth2client.file import Storage

# When deploying on virtual machines without IaaS support.
CLUSTER_DEPLOY = "cluster"

# When deploying on IaaS such as EC2 or Eucalyptus.
CLOUD_DEPLOY = "cloud"

# A global variable to store all threads deploying AppScale.
DEPLOYMENT_THREADS = {}

# A global variable to store all threads terminating AppScale.
TERMINATING_THREADS = {}

# Placement stategies for cloud deployments.
SIMPLE_DEPLOYMENT = "simple"
ADVANCE_DEPLOYMENT = "advanced"

# The location of template files.
TERMINATE_HTML_FILE_PATH = "base/terminate.html"
HOMEPAGE_HTML_FILE_PATH = "base/home.html"
ABOUT_HTML_FILE_PATH = "base/about.html"
APPSCALE_STARTED_HTML_FILE_PATH = "base/start.html"

def terminate(request):
  """ A request to the terminate page which goes and looks up a currently 
  running deployment and terminates that deployment.
  
  Args:
    request: A Django web request.
  Returns:
    A rendered version of terminate.html with the keyname passed into the 
    javascript.
  """
  get = request.GET.copy()
  if 'keyname' not in get:
    return HttpResponseServerError("Did not receive the keyname of the " \
      "instances to terminate.")

  keyname = get['keyname']
  if keyname not in DEPLOYMENT_THREADS:
    return HttpResponseServerError("Unknown keyname of the " \
      "instances to terminate.")

  appscale_up_thread = DEPLOYMENT_THREADS[keyname]

  terminate_thread = appscale_tools_thread.AppScaleDown(
    appscale_up_thread.deployment_type, keyname,
    ec2_access=appscale_up_thread.ec2_access, 
    ec2_secret=appscale_up_thread.ec2_secret,
    ec2_url=appscale_up_thread.ec2_url)

  TERMINATING_THREADS[keyname] = terminate_thread

  terminate_thread.start()

  return render(request, TERMINATE_HTML_FILE_PATH, {'keyname': keyname})

def home(request):
  """ Render the home page which takes in input from the user to start 
  AppScale. 

  Args:
    request: A Django web request.
  Returns:
    A rendered version of home.html with form fields.
  """
  return render(request, HOMEPAGE_HTML_FILE_PATH, {'form': CommonFields()})

def about(request):
  """ Render the about page that tells users about AppsCake. 

  Args:
    request: A Django web request.
  Returns:  
    A rendered version of about.html. 
  """
  return render(request, ABOUT_HTML_FILE_PATH)

def get_deployment_status(request):
  """ Returns a json string of the status of the tools being run.

  Args:
    request: A Django web request.
  Returns:
    A HttpResponse object with a json message of the current deployment status.
  """
  get = request.GET.copy()
  identifier = None
  if 'keyname' in get:
    identifier = get['keyname']
  else:
    message = {'status': 'error', 'error_message': 
      "Bad JSON request (missing keyname)."}
    return HttpResponse(simplejson.dumps(message))  

  logging.debug("Running keyname {0}".format(DEPLOYMENT_THREADS.keys()))

  if identifier not in DEPLOYMENT_THREADS:
    message = {'status': 'error', 'error_message': 
      "Unknown keyname given {0}.".format(identifier)}
  else:
    message = DEPLOYMENT_THREADS[identifier].get_status()

  return HttpResponse(simplejson.dumps(message))  

def get_termination_status(request):
  """ Returns a json string of the status of the tools being run.

  Returns:
    A HttpResponse object with a json message of the current termination status.
  """
  get = request.GET.copy()
  identifier = None
  if 'keyname' in get:
    identifier = get['keyname']
  else:
    message = {'status': 'error', 'error_message': 
      "Bad JSON request (missing keyname)."}
    return HttpResponse(simplejson.dumps(message))  

  if identifier not in TERMINATING_THREADS:
    message = {'status': 'error', 'error_message': 
      "Unknown keyname given {0}.".format(identifier)}
  else:
    message = TERMINATING_THREADS[identifier].get_status()

  return HttpResponse(simplejson.dumps(message))  


def oauth2_callback(request):
  if request.method == 'GET':
    # Generate oauth2.dat file based on code in query string.
    code = request.GET.get('code','')
    client_id = request.COOKIES.get('client_id')
    helpers.save_gce_credentials(client_id, code)
    oauth2_location = ('.data/.credentials-%s.dat' % client_id)

    # Get decrypted form data from cookie.
    cookie_data = request.COOKIES.get('data')
    form_data = helpers.get_decrypted_cookie_data(client_id, cookie_data)
    json_data = json.loads(form_data)
    
    # Get form parameters from decrypted json.
    email = json_data[0]['email']
    password = json_data[0]['password']
    deployment_type = json_data[0]['deployment_type']
    instance_type = json_data[0]['instance_type']
    client_secrets = json_data[0]['client_secrets']
    gce_image_name = json_data[0]['gce_image_name']
    project = json_data[0]['project']

    # These are defaults for a GCE deployment
    keyname = helpers.generate_keyname()
    cloud_type = CLOUD_DEPLOY
    infras = 'gce'
    machine = gce_image_name

    if deployment_type == ADVANCE_DEPLOYMENT:
      ips_yaml = form['ips_yaml'].value()
      appscale_up_thread = appscale_tools_thread.AppScaleUp(cloud_type,
                                 keyname,
                                 email,
                                 password,
                                 placement=ADVANCE_DEPLOYMENT,
                                 machine=machine,
                                 instance_type=instance_type,
                                 infrastructure=infras,
                                 ips_yaml=ips_yaml,
                                 oauth2_location=oauth2_location,
                                 project_id=project)
    elif deployment_type == SIMPLE_DEPLOYMENT:
      min_nodes = max_nodes = json_data[0]['max_nodes']
      appscale_up_thread = appscale_tools_thread.AppScaleUp(cloud_type,
                                 keyname,
                                 email,
                                 password,
                                 placement=SIMPLE_DEPLOYMENT,
                                 machine=machine,
                                 instance_type=instance_type,
                                 infrastructure=infras,
                                 max_nodes=max_nodes,
                                 min_nodes=min_nodes,
                                 oauth2_location=oauth2_location,
                                 project_id=project)
    else:
      return HttpResponseServerError("Unable to get the deployment strategy.")
    appscale_up_thread.start()

    identifier = appscale_up_thread.keyname
    DEPLOYMENT_THREADS[identifier] = appscale_up_thread

    return render(request, APPSCALE_STARTED_HTML_FILE_PATH, {'keyname':
      identifier})

  else:
    return HttpResponseServerError("404 Page not found")
   

def start(request):
  """ This is the page a user submits a request to start AppScale. 

  Returns:
    A HttpResponse rendering the start page or HttpResponseServerError
    if there was an error.
  """
  if request.method == 'POST':
    form = CommonFields(data=request.POST)
    appscale_up_thread = None
    email = form['admin_email'].value()
    password = form['admin_pass'].value() or form['cloud_admin_pass'].value()
    keyname = helpers.generate_keyname()
    cloud_type = None
    if 'cluster' in request.POST:
      cloud_type = CLUSTER_DEPLOY
    elif 'cloud' in request.POST:
      cloud_type = CLOUD_DEPLOY

    if cloud_type == CLOUD_DEPLOY:
      infras = form['infrastructure'].value()
      deployment_type = form['deployment_type'].value()
      instance_type = form['instance_type'].value()
      machine = form['machine'].value()
      instance_type = form['instance_type'].value()
      access_key = form['key'].value()
      secret_key = form['secret'].value()
      ec2_url = form['ec2_euca_url'].value()
      client_secrets = form['gceCredentials'].value()
      project = form['gceProjectId'].value()
      gce_image_name = form['gceImageName'].value()
      min_nodes = max_nodes = form['max'].value()
  
      if 'gce' == form['infrastructure'].value():
        machine = form['gceImageName'].value()
        client_id = helpers.get_client_id_from_client_secrets(client_secrets)
        # Always delete old credentials if they exist, they may have expired.
        helpers.delete_old_credentials(client_id)
        redirect_uri = helpers.get_auth_server_uri(client_secrets)
        response = HttpResponseRedirect(str(redirect_uri))
        form_data_as_json = helpers.get_form_data_as_json_string(email,
          password, max_nodes, deployment_type, instance_type,
          gce_image_name, project, client_secrets)
        response.set_cookie('data',
          helpers.get_encrypted_cookie_data(client_id, form_data_as_json))
        response.set_cookie('client_id', client_id)
        return response

      if not ec2_url:
        ec2_url = None

      if deployment_type == ADVANCE_DEPLOYMENT:
        ips_yaml = form['ips_yaml'].value()
        appscale_up_thread = appscale_tools_thread.AppScaleUp(cloud_type,
                                   keyname,
                                   email,
                                   password,
                                   placement=ADVANCE_DEPLOYMENT,
                                   machine=machine,
                                   instance_type=instance_type,
                                   infrastructure=infras,
                                   ips_yaml=ips_yaml,
                                   ec2_access=access_key,
                                   ec2_secret=secret_key,
                                   ec2_url=ec2_url)
      elif deployment_type == SIMPLE_DEPLOYMENT:
        min_nodes = max_nodes = form['max'].value()
        appscale_up_thread = appscale_tools_thread.AppScaleUp(cloud_type,
                                   keyname,
                                   email,
                                   password,
                                   placement=SIMPLE_DEPLOYMENT,
                                   machine=machine,
                                   instance_type=instance_type,
                                   infrastructure=infras,
                                   max_nodes=max_nodes,
                                   min_nodes=min_nodes,
                                   ec2_access=access_key,
                                   ec2_secret=secret_key,
                                   ec2_url=ec2_url)
      else:
        return HttpResponseServerError("Unable to get the deployment strategy.")
    elif cloud_type == CLUSTER_DEPLOY:
      ips_yaml = form['ips_yaml'].value()
      root_password = form['root_pass'].value()
      appscale_up_thread = appscale_tools_thread.AppScaleUp(cloud_type, 
                                   keyname,  
                                   email,
                                   password,
                                   ips_yaml=ips_yaml,
                                   root_pass=root_password)
    else:
      return HttpResponseServerError(
        "Unable to figure out the type of cloud deployment.")  

    appscale_up_thread.start()

    identifier = appscale_up_thread.keyname
    DEPLOYMENT_THREADS[identifier] = appscale_up_thread

    return render(request, APPSCALE_STARTED_HTML_FILE_PATH, {'keyname': 
      identifier})
  else:
    return HttpResponseServerError("404 Page not found")

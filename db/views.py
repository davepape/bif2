from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login,authenticate
from django.template import loader
from django.core.mail import EmailMultiAlternatives

from .models import *

import json

def index(request):
    if request and hasattr(request,'user') and hasattr(request.user,'bifuser'):
        owned = request.user.bifuser.permit_what.filter(permission=UserPermission.OWNER)
    else:
        owned = None
    return render(request,'db/index.html', { 'owned':owned })


def allProposals(request):
    props = Proposal.objects.all()
    return render(request,'db/index.html', { 'prop_list' : props })


def batches(request):
    batchlist = Batch.objects.all()
    return render(request,'db/batches.html', { 'batchlist' : batchlist })


def submit(request):
    infodict = {}
    infodict = request.POST.copy()
    for k in ['title','csrfmiddlewaretoken']:
        if k in infodict.keys():
            del infodict[k]

    defaultContact = None
    defaultBatch = None
    if 'type' in infodict.keys():
        try:
            formInfo = FormInfo.objects.get(showType=infodict['type'])
            defaultContact = formInfo.defaultContact
            defaultBatch = formInfo.defaultBatch
        except:
            pass

    infojson = json.dumps(infodict)
    prop = Proposal(title=request.POST["title"], info=infojson, status=Proposal.WAITING, orgContact=defaultContact)
    prop.save()
    logInfo("saved proposal {ID:%d} ('%s')" % (prop.id,prop.title), request)

    mail_to = infodict["contactemail"]
    from django.core.validators import validate_email
    from django.core.exceptions import ValidationError
    try:
        validate_email( mail_to )
    except ValidationError:
        logInfo("email '%s' is invalid" % mail_to)
        return render(request,'db/proposal_email_fail.html', {'address':mail_to})
    context = {'prop':prop, 'prop_info':infodict}
    mail_subject = "Buffalo Infringement Festival proposal '%s'" % prop.title
    mail_body = loader.render_to_string('db/submit_email.txt', context)
    if defaultContact:
        cc_list = [ defaultContact.user.email ]
    else:
        cc_list = None
    EmailMultiAlternatives(mail_subject, mail_body, None, [mail_to], cc=cc_list).send()
    if defaultBatch:
        defaultBatch.members.add(prop)
        logInfo("Added {ID:%d} to batch {ID:%d}"%(prop.id,defaultBatch.id), request)
    return render(request,'db/proposal_submit.html', {})


def setEntityOwner(e,u):
# need to: check if already owned by someone else, and change it (if allowed)
    if UserPermission.objects.filter(entity=e,bifuser=u).count() == 0:
        permit = UserPermission(entity=e, bifuser = u, permission=UserPermission.OWNER)
        permit.save()


def confirmProposal(request,id):
    prop = get_object_or_404(Proposal, pk=id)
    prop.status = Proposal.ACCEPTED     # Note that this will also undelete a deleted proposal - will leave it that way for now
    propinfodict = json.loads(prop.info)
    try:
        owner = User.objects.get(username=propinfodict["contactemail"])
        setEntityOwner(prop, owner.bifuser)
    except:
        pass
    prop.save()
    logInfo("confirmed proposal {ID:%d}" % id, request)
    return render(request,'db/proposal_confirm.html', {'title':prop.title})


def proposalForm(request, template):
    days = ["July 26 (Thu)", "July 27 (Fri)","July 28 (Sat)","July 29 (Sun)","July 30 (Mon)","July 31 (Tue)","Aug 1 (Wed)","Aug 2 (Thu)","Aug 3 (Fri)","Aug 4 (Sat)","Aug 5 (Sun)"]
    times = [("8am", "8am-noon"), ("noon", "noon-4pm"), ("4pm", "4pm-8pm"), ("8pm", "8pm-midnight"), ("mid", "midnight-4am")]
    context = {'daylist':days, 'timelist':times}
    return render(request, template, context)


def musicForm(request):
    return proposalForm(request, 'db/music_form.html')

def theatreForm(request):
    return proposalForm(request, 'db/theatre_form.html')

def visualartForm(request):
    return proposalForm(request, 'db/visualart_form.html')

def danceForm(request):
    return proposalForm(request, 'db/dance_form.html')

def literaryForm(request):
    return proposalForm(request, 'db/literary_form.html')

def filmForm(request):
    return proposalForm(request, 'db/film_form.html')


def newAccount(request):
    return render(request,'db/new_account.html', {})


from django.contrib.auth.models import User

def createAccount(request):
    from django.db.utils import IntegrityError
    email = request.POST['email']
    password = request.POST['password']
    try:
        djuser = User.objects.create_user(email, email, password)
    except IntegrityError:
        logError("Tried to create duplicate account '%s'"%email, request)
        err = "An account '%s' already exists" % email
        return render(request, 'db/new_account.html', { 'error': err })
    except:
        logError("Unknown error creating account '%s'"%email, request)
        return render(request, 'db/new_account.html', { 'error': 'Failed to create account.' })
    bifuser = BIFUser.objects.create(user=djuser, phone='555-1212')
    login(request, authenticate(username=email,password=password))
    logInfo("Created new account '%s'"%email, request)
    return redirect('index')


def newBatch(request):
    return render(request,'db/new_batch.html', {})


def createBatch(request):
    name = request.POST['name']
    description = request.POST['description']
    try:
        batch = Batch(name=name, description=description, festival=None)
    except:
        logError("Unknown error creating batch '%s'"%name, request)
        return render(request, 'db/new_batch.html', { 'error': 'Failed to create batch.' })
    batch.save()
    logInfo("Created new batch {ID:%d} '%s'"%(batch.id,name), request)
    return redirect('index')


@login_required
def addToBatch(request,batchid,memberid):
    b = get_object_or_404(Batch, pk=batchid)
    m = get_object_or_404(Entity, pk=memberid)
    b.members.add(m)
    logInfo("Added {ID:%d} to batch {ID:%d}"%(memberid,batchid), request)
    return redirect('entity',id=batchid)

@login_required
def addToBatchForm(request):
    batchid = int(request.POST['batch'])
    memberid = int(request.POST['show'])
    return addToBatch(request,batchid,memberid)


@login_required
def entity(request,id):
    e = get_object_or_404(Entity, pk=id)
    if e.entityType == 'proposal':
        return proposal(request,id)
    elif e.entityType == 'batch':
        return batch(request,id)
    else:
        return render(request, 'db/entity_error.html', { 'type': e.entityType })


@login_required
def proposal(request,id):
    prop = get_object_or_404(Proposal, pk=id)
    infodict = json.loads(prop.info)
    inbatches = prop.batches.all()
    batches = Batch.objects.all()
    context = {'prop':prop, 'prop_info':infodict, 'inbatches':inbatches, 'batches':batches}
    return render(request,'db/proposal.html', context)


@login_required
def batch(request,id):
    b = get_object_or_404(Batch, pk=id)
    memberlist = []
    for e in b.members.all():
        memberlist.append({'id':e.id,'name':entityName(e)})
    props = Proposal.objects.all()
    context = {'batch':b, 'members':memberlist, 'proposals':props}
    return render(request,'db/batch.html', context)


def entityName(e):
    if e.entityType == 'proposal':
        return e.proposal.title
    elif e.entityType == 'batch':
        return e.batch.name
    elif e.entityType == 'venue':
        return e.venue.name
    else:
        return "%s %d" % (e.entityType,e.id)


import logging

def logInfo(message,request=None):
    logger = logging.getLogger(__name__)
    logger.info(logMessage(message,request))


def logError(message,request=None):
    logger = logging.getLogger(__name__)
    logger.error(logMessage(message,request))


def logMessage(message,request=None):
    from datetime import datetime
    username = 'anonymous-user'
    if request and hasattr(request,'user') and hasattr(request.user,'username') and request.user.username != '':
        username = request.user.username
    ipaddr = 'ip-unknown'
    if request:
        ipaddr = request.META.get('REMOTE_ADDR')
    return "%s %s %s: %s" % (datetime.now().strftime("%Y-%m-%d %X"),ipaddr,username, message)


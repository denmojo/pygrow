from . import base
from googleapiclient import discovery
from googleapiclient import errors
from grow.common import oauth
from grow.common import utils
import base64
import httplib2
import json
import logging
import urllib

EDIT_URL_FORMAT = 'https://translate.google.com/toolkit/workbench?did={}'
GTT_DOCUMENTS_BASE_URL = 'https://www.googleapis.com/gte/v1/documents'
OAUTH_SCOPE = 'https://www.googleapis.com/auth/gte'
STORAGE_KEY = 'Grow SDK - Google Translator Toolkit'


class AccessLevel(object):
    ADMIN = 'ADMIN'
    READ_AND_COMMENT = 'READ_AND_COMMENT'
    READ_AND_WRITE = 'READ_AND_WRITE'
    READ_ONLY = 'READ_ONLY'


class ChangeType(object):
    MODIFY = 'MODIFY'
    ADD = 'ADD'


def raise_api_error(resp):
    # TODO: Create and use base error class.
    resp = json.loads(resp.content)['error']
    logging.error('GTT Request Error {}: {}'.format(resp['code'], resp['message']))
    for each_error in resp['errors']:
        logging.error('{}: {}'.format(each_error['message'], each_error['reason']))
    raise


class Gtt(object):

    def __init__(self):
        self.service = discovery.build('gte', 'v1', http=self.http)

    @property
    def http(self):
        credentials = oauth.get_credentials(
            scope=OAUTH_SCOPE, storage_key=STORAGE_KEY)
        http = httplib2.Http(ca_certs=utils.get_cacerts_path())
        http = credentials.authorize(http)
        return http

    def get_document(self, document_id):
        return self.service.documents().get(documentId=document_id).execute()

    def get_user_from_acl(self, document_id, email):
        document = self.get_document(document_id)
        for user in document['gttAcl']:
            if user.get('emailId') == email:
                return user

    def update_acl(self, document_id, email, access_level, can_reshare=True, update=False):
        acl_change_type = ChangeType.MODIFY if update else ChangeType.ADD
        body = {
            'gttAclChange': {
                [
                    {
                        'accessLevel': access_level,
                        'canReshare': can_reshare,
                        'emailId': email,
                        'type': acl_change_type,
                    }
                ]
            }
        }
        return self.service.documents().update(
            documentId=document_id, body=body).execute()

    def share_document(self, document_id, email, access_level=AccessLevel.READ_AND_WRITE):
        in_acl = self.get_user_from_acl(document_id, email)
        update = True if in_acl else False
        return self.update_acl(document_id, email, access_level=access_level, update=update)

    def insert_document(self, name, content, source_lang, lang, mimetype, acl_emails=None):
        acl = None
        if acl_emails:
            acl = [{
                'emailId': email,
                'accessLevel': AccessLevel.READ_AND_WRITE,
            } for email in acl_emails]
        content = base64.urlsafe_b64encode(content)
        doc = {
            'displayName': name,
            'gttAcl': acl,
            'language': lang,
            'mimetype': mimetype,
            'sourceDocBytes': content,
            'sourceLang': source_lang,
        }
        try:
            return self.service.documents().insert(body=doc).execute()
        except errors.HttpError as resp:
            raise_api_error(resp)

    def download_document(self, document_id):
        params = {
            'alt': 'media',
            'downloadContent': True,
        }
        url = '{}/{}?{}'.format(GTT_DOCUMENTS_BASE_URL, urllib.quote(document_id), urllib.urlencode(params))
        response, content = self.http.request(url)
        # TODO: Create and use base error class.
        try:
            if response.status >= 400:
                raise errors.HttpError(response, content, uri=url)
        except errors.HttpError as resp:
            raise_api_error(resp)
        return content


class GoogleTranslatorToolkitTranslator(base.Translator):
    KIND = 'google_translator_toolkit'

    def _normalize_source_lang(self, source_lang):
        if source_lang is None:
            return 'en'
        source_lang = str(source_lang)
        source_lang = source_lang.lower()
        if source_lang == 'en_us':
            return 'en'
        return source_lang

    def _upload_catalog(self, catalog, source_lang):
        gtt = Gtt()
        project_title = self.config.get('project_title', 'Untitled Grow Project')
        name = '{} ({})'.format(project_title, str(catalog.locale))
        source_lang = self._normalize_source_lang(source_lang)
        resp = gtt.insert_document(
            name=name,
            content=catalog.content,
            source_lang=str(source_lang),
            lang=str(catalog.locale),
            mimetype='text/x-gettext-translation')
        # TODO: Create and use base UploadCatalogResponse class.
        return resp

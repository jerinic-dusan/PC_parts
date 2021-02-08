import json, nltk, re, requests, smtplib, time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from bs4 import BeautifulSoup

from string import punctuation
from nltk.corpus import stopwords
from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager

# Get your api key from https://newsapi.org/

# Storing gathered data
data = {}
# Data example
# {
#    "Ryzen 5 3600": {
#       "product_info": {
#          "name": "Ryzen 5 3600",
#          "image": "cdna.pcpartpicker.com/static/forever/images/product/c7baf2c9c9cc15ae23adb24c2f4316fc.256p.jpg"
#       },
#       "vendors": [
#          {
#             "name": "Newegg",
#             "price": "$194.99",
#             "url": "pcpartpicker.com/mr/newegg/9nm323"
#          }
#       ],
#       "articles": [
#          {
#             "title": "Is Zen 3 Worth It for Gaming? Ryzen 5600X vs. 3600 vs. Core i5-10400F",
#             "url": "https://www.techspot.com/review/2185-amd-zen-3-ryzen-5600-versus/"
#          }
#       ],
#       "article_summarization": "We check out Intel's Core i5-10400F, a direct competitor to the Ryzen 3600 to see how this budget CPU performs when paired with a last-generation high-end Radeon gaming GPU."
#    }
# }

# Setting up webdriver for scraping

options = webdriver.ChromeOptions()
options.add_argument('headless')
driver = webdriver.Chrome(ChromeDriverManager().install(), options=options)


# Data scraping
def scrape_data(product):
    print('Scraping data for ' + product['product_name'] + '...')
    data[product['product_name']] = {'product_info': {'name': product['product_name'], 'image': ''}, 'vendors': [], 'articles': [], 'article_summarization': ''}
    driver.get(product['product_link'])
    time.sleep(0.5)
    html = driver.page_source
    soup = BeautifulSoup(html, 'html.parser')

    # Scraping image
    gallery = soup.find('section', {'class': 'productGallery__wrapper'})
    if gallery:
        image = gallery.find('div', {'class': 'gallery__images'}).find_all('img')[0].get('src')[2:]
    else:
        image = soup.find('div', {'id': 'single_image_gallery_box'}).find('img').get('src')[2:]
    data[product['product_name']]['product_info']['image'] = image

    # Scraping vendors
    vendors_counter = 0
    rows = soup.find('div', {'id': 'prices'}).find('tbody').find_all('tr', {'class': ''})
    for row in rows:
        if vendors_counter == 3:
            break
        if row.find('td', {'class': 'td__availability td__availability--outOfStock'}, recursive=False):
            continue
        vendor = {'name': '', 'price': '', 'url': ''}
        name_link = row.find('td', {'class': 'td__logo'})
        vendor['name'] = name_link.find('img').get('alt')
        vendor['url'] = 'pcpartpicker.com' + name_link.find('a').get('href')
        vendor['price'] = row.find('td', {'class': 'td__finalPrice'}).find('a').text
        data[product['product_name']]['vendors'].append(vendor)
        vendors_counter += 1


# News fetching
def fetch_news(product):
    print('Fetching news for ' + product['product_name'] + '...')

    # Opening file with api key
    with open("apikey.json") as file:
        api_key = json.load(file)

    # Fetching data from api
    url = r'https://newsapi.org/v2/everything?apiKey=' + api_key['api_key'] + '&language=en&q=' + product['product_name'] + '&pageSize=3'
    request_object = requests.get(url)
    result = request_object.json()

    articles = []
    for res in result['articles']:
        article = {'title': res['title'], 'url': res['url']}
        articles.append(article)

    # Getting data for NLP (text summarization)
    nlp_data = []
    sentences = []
    stop_punc = set(stopwords.words('english')).union(set(punctuation))     # stop words from english language that will be removed

    tags_pattern = '\<[^>]*\>'                                              # pattern matches tags and everything in between
    spaces_pattern = r'\s+'                                                 # pattern matches extra spaces
    alphanumeric_dollar_pattern = '[^A-Za-z0-9 $\']'                        # pattern matches alphanumeric characters including dollar sign and ' char

    for article in result['articles']:

        # Cleaning and extracting sentences
        desc_tags = re.sub(tags_pattern, ' ', article['description'])
        desc_clean = re.sub(spaces_pattern, ' ', desc_tags)
        for sent in nltk.sent_tokenize(desc_clean): sentences.append(sent)

        # Cleaning and extracting words for vocabulary
        desc = re.sub(alphanumeric_dollar_pattern, ' ', desc_clean)
        desc_words = desc.split()
        desc_words_clean = [word for word in desc_words if word not in stop_punc and len(word) >= 3]
        for word in desc_words_clean: nlp_data.append(word)

    # Adding words to vocabulary
    vocabulary = {}
    for word in nlp_data:
        if word not in vocabulary.keys():
            vocabulary[word] = 1.0
        else:
            vocabulary[word] += 1.0

    # Calculating word frequencies
    max_word_counter = max(vocabulary.values())
    for word in vocabulary: vocabulary[word] /= max_word_counter

    # Calculating sentence score based on word frequencies that show up in them
    sentence_scores = {}
    for sent in sentences:
        for word in sent.split():
            if word in vocabulary.keys():
                if sent not in sentence_scores.keys():
                    sentence_scores[sent] = 0
                else:
                    sentence_scores[sent] += vocabulary[word]

    # Sorting sentences and adding most important one
    sorted_scores = dict(sorted(sentence_scores.items(), key=lambda x: x[1], reverse=True))
    data[product['product_name']]['article_summarization'] = list(sorted_scores.keys())[0]
    data[product['product_name']]['articles'] = articles
    file.close()


# Mail sending
def send_mail():
    print('Sending mail...')

    # Opening file with needed information
    with open("email.json") as file:
        email = json.load(file)
    sender = email['sender']
    receiver = email['receiver']
    password = email['sender_pass']

    # Setting up the server
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.ehlo()
    server.starttls()
    server.ehlo()
    server.login(sender, password)

    # Mail header information
    message = MIMEMultipart("alternative")
    message["Subject"] = "Newest prices for your products!"
    message["From"] = sender
    message["To"] = receiver

    text = console_print()
    html = """
        <html>
            <body>
        """
    html_end = """
            </body>
        </html>
        """
    for key in data.keys():
        html += f"""
            <h2>{data[key]['product_info']['name']}:</h2>
            <div class="product" style="display: flex;">
                <div class="product_left" style="margin-right:1%;">
                    <img src="{data[key]['product_info']['image']}" alt="image" width="130" height="130"/>
                </div>
                <div class="product_right">
        """
        for vendor in data[key]['vendors']:
            html += f"""<h4><a href="{vendor['url']}" style="text-decoration: none">• {vendor['name'] + ': ' + vendor['price']}</a></h4>\n"""

        html += f"""
                </div>
            </div>
            <h3>Related articles:</h3>\n
            """
        for article in data[key]['articles']:
            html += f"""
                <h4><a href="{article['url']}" style="text-decoration: none">• {article['title']}</a><h4>
            """
        html += f"""
            <h3>Text summarization:</h3>\n
            <h4>{data[key]['article_summarization']}</h4>
            <hr>
        """

    html += html_end

    message.attach(MIMEText(text, "plain"))
    message.attach(MIMEText(html, "html"))
    server.sendmail(sender, receiver, message.as_string())
    server.close()
    file.close()
    print('Mail sent.')


# Console printing
def console_print():
    separator = '--------------------------------------------------|--------------------------------------------------\n'
    text = separator
    for key in data.keys():
        text += data[key]['product_info']['name'] + ':\n'
        for vendor in data[key]['vendors']:
            text += '• ' + vendor['name'] + ' ' + vendor['price'] + ' - https://www.' + vendor['url'] + '\n'
        text += 'Related articles:\n'
        for article in data[key]['articles']:
            text += '• ' + article['title'] + ' - ' + article['url'] + '\n'
        text += 'Text summarization: ' + data[key]['article_summarization'] + '\n'
        text += separator
    return text


if __name__ == '__main__':
    # Option selection
    acceptable_options = ['Y', 'y', 'N', 'n']
    option = ''
    while option not in acceptable_options:
        option = input("Please selected if you want data to be sent by mail or displayed in console. (Y-send mail, N-console): ")

    # Opening the file with wanted products
    with open("products.json") as f: products = json.load(f)

    for p in products:
        scrape_data(p)
        fetch_news(p)
    f.close()

    option = option.lower()
    if option == 'y':
        send_mail()
    else:
        print('Printing data to console...\n', console_print())

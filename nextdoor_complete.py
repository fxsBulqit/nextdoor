#!/usr/bin/env python3
"""
Complete Nextdoor Scanner for Bulqit Service Opportunities
Consolidated single file with all dependencies included
"""

import time
import random
import re
import os
import requests
import json
import smtplib
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from groq import Groq

# Bulqit Context and Guidelines
BULQIT_CONTEXT = """
Bulqit is a comprehensive home service platform operating in the San Fernando Valley area of Los Angeles.
We provide bulk pricing for multiple home services including:

🏊 Pool Services: Cleaning, maintenance, chemical balancing, equipment repair
🌱 Lawn Care: Mowing, landscaping, irrigation, tree trimming, weed control
🐛 Pest Control: Ants, rats, termites, general extermination, prevention
🪟 Window Washing: Residential cleaning services, gutter cleaning
🔧 Handyman: Repairs, maintenance, installations, general contractor work

Our key value proposition is bulk neighborhood pricing - when multiple neighbors sign up for the same service, everyone gets a discount. We focus on reliability, quality, and community savings.

Target areas: Sherman Oaks, Studio City, Encino, Tarzana, Woodland Hills, Canoga Park, Reseda, Northridge, Van Nuys, North Hollywood, Valley Village, Panorama City, Sun Valley, Granada Hills.
"""

RESPONSE_GUIDELINES = """
When generating responses for social media posts:
1. Be helpful and natural, not salesy
2. Mention Bulqit as a neighborhood-focused solution
3. Emphasize the bulk pricing advantage
4. Keep responses under 150 words
5. Include a soft call-to-action about checking out Bulqit
6. Don't sound like an advertisement
7. Focus on solving their specific problem
"""

class BulqitGroqClient:
    def __init__(self):
        # Load API keys from keys.txt or environment
        try:
            keys_paths = ['keys.txt', '../keys.txt']
            self.api_keys = []

            for path in keys_paths:
                try:
                    with open(path, 'r') as f:
                        self.api_keys = [line.strip() for line in f.readlines() if line.strip()]
                    break
                except FileNotFoundError:
                    continue

            if not self.api_keys:
                # Try environment variables
                env_keys = [
                    os.getenv('GROQ_API_KEY_1'),
                    os.getenv('GROQ_API_KEY_2'),
                    os.getenv('GROQ_API_KEY_3'),
                    os.getenv('GROQ_API_KEY_4'),
                    os.getenv('GROQ_API_KEY_5')
                ]
                self.api_keys = [key for key in env_keys if key]

        except Exception:
            # Final fallback to single env var
            single_key = os.getenv('GROQ_API_KEY')
            self.api_keys = [single_key] if single_key else []

        if not self.api_keys:
            raise ValueError("No API keys found in keys.txt or environment variables")

        self.current_key_index = 0
        self.client = Groq(api_key=self.api_keys[0])
        self.model = "meta-llama/llama-4-scout-17b-16e-instruct"
        self.daily_request_count = 0
        self.max_requests_per_key = 95

    def _rotate_api_key(self):
        """Rotate to next API key when current one hits limit"""
        if self.current_key_index < len(self.api_keys) - 1:
            self.current_key_index += 1
            self.client = Groq(api_key=self.api_keys[self.current_key_index])
            self.daily_request_count = 0
            print(f"🔄 Rotated to API key {self.current_key_index + 1}/{len(self.api_keys)}")
            return True
        else:
            print("❌ All API keys exhausted for today")
            return False

class EmailSender:
    def __init__(self, smtp_server="smtp.gmail.com", smtp_port=587):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port

    def send_daily_report(self, report_content, recipient_emails=["fxs@bulqit.com", "tjv@bulqit.com", "kjb@bulqit.com"]):
        """Send daily report via email"""
        subject = f"Bulqit Daily Social Media Opportunities - {datetime.now().strftime('%Y-%m-%d')}"
        return self._send_with_custom_subject(report_content, recipient_emails, subject)

    def _send_with_custom_subject(self, report_content, recipient_emails, custom_subject, json_attachment=None):
        """Send daily report via email with custom subject and optional JSON attachment"""
        sender_email = os.getenv('BULQIT_EMAIL')
        sender_password = os.getenv('BULQIT_EMAIL_PASSWORD')

        if not sender_email or not sender_password:
            print("❌ Email credentials not set")
            return False

        try:
            # Create message
            msg = MIMEMultipart()
            msg['From'] = f"Bulqit Social Monitor <{sender_email}>"
            msg['To'] = ", ".join(recipient_emails)
            msg['Subject'] = custom_subject

            # Add body
            msg.attach(MIMEText(report_content, 'plain'))

            # Add JSON attachment if provided
            if json_attachment:
                from email.mime.application import MIMEApplication

                json_data = json.dumps(json_attachment, indent=2, ensure_ascii=False)
                json_attachment_obj = MIMEApplication(json_data.encode('utf-8'), Name=f"nextdoor_posts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
                json_attachment_obj['Content-Disposition'] = f'attachment; filename="nextdoor_posts_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json"'
                msg.attach(json_attachment_obj)
                print(f"📎 Added JSON attachment with {len(json_attachment)} posts")

            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(sender_email, sender_password)
                text = msg.as_string()
                server.sendmail(sender_email, recipient_emails, text)

            print(f"✅ Email sent successfully to {recipient_emails}")
            return True

        except Exception as e:
            print(f"❌ Failed to send email: {str(e)}")
            return False

class NextdoorGroqFilter:
    def __init__(self, groq_client, email_sender):
        self.groq_client = groq_client
        self.email_sender = email_sender

    def analyze_nextdoor_post(self, post_text, author):
        """Analyze if a Nextdoor post is relevant for Bulqit"""
        try:
            prompt = f"""
            Analyze this Nextdoor post for relevance to home services that Bulqit provides (lawn care, pool maintenance, pest control, window cleaning, handyman work, contractors, plumbers, electricians, roofers, cleaning services).

            Post Author: {author}
            Post Text: {post_text}

            Return ONLY a JSON object with:
            {{
                "relevant": true/false,
                "service_type": "lawn_care|pool|pest_control|window_cleaning|handyman|contractor|plumber|electrician|roofer|cleaning|general|none",
                "reason": "brief explanation"
            }}

            Answer TRUE if the post is:
            - Asking for recommendations for ANY home service provider
            - Complaining about service providers (contractors, cleaners, etc.)
            - Describing home maintenance/repair problems needing professional help
            - Looking for help with home repairs, maintenance, or improvements
            - Seeking quotes or estimates for home work
            - Posts about bad experiences with contractors/service providers
            - Offering services (potential competitor intelligence)

            Answer FALSE if the post is:
            - General neighborhood discussions unrelated to services
            - Food/restaurant recommendations
            - Lost pets or general community announcements
            - Social events or activities
            - Crime/safety discussions
            - Political discussions
            - Simple questions about local businesses unrelated to home services

            Be decisive - answer TRUE or FALSE only.
            """

            response = self.groq_client.client.chat.completions.create(
                model=self.groq_client.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=250
            )

            self.groq_client.daily_request_count += 1

            # Parse JSON response
            content = response.choices[0].message.content.strip()

            # Clean up response
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content:
                content = content.split('```')[1].split('```')[0].strip()

            # Find JSON in response
            if not content.startswith('{'):
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    content = json_match.group()

            return json.loads(content)

        except Exception as e:
            error_str = str(e)
            print(f"Error analyzing Nextdoor post: {error_str}")

            # Check if it's a rate limit error and try to rotate keys
            if "rate_limit_exceeded" in error_str or "429" in error_str:
                print("🔄 Rate limit hit - attempting to rotate API key...")
                if self.groq_client._rotate_api_key():
                    # Retry with new key
                    return self.analyze_nextdoor_post(post_text, author)
                else:
                    print("❌ All API keys exhausted")
                    return {"relevant": False, "reason": "all_keys_exhausted"}

            return {"relevant": False, "reason": f"analysis_error: {error_str}"}

    def filter_posts(self, posts):
        """Filter posts and return only relevant ones with analysis"""
        relevant_posts = []

        print(f"🔍 Analyzing {len(posts)} Nextdoor posts with Groq...")

        for i, post in enumerate(posts):
            try:
                print(f"📝 Analyzing post {i+1}/{len(posts)} by {post['author']}")

                analysis = self.analyze_nextdoor_post(post['text'], post['author'])

                if analysis.get('relevant', False):
                    post['analysis'] = analysis
                    relevant_posts.append(post)
                    print(f"✅ RELEVANT: {post['text'][:60]}... ({analysis.get('service_type', 'general')})")
                else:
                    print(f"❌ Not relevant: {analysis.get('reason', 'Unknown')}")

                # Small delay to avoid rate limiting
                time.sleep(0.5)

            except Exception as e:
                print(f"⚠️ Error analyzing post {i+1}: {str(e)}")
                continue

        print(f"📊 Found {len(relevant_posts)} relevant posts out of {len(posts)} total")
        return relevant_posts

    def generate_report(self, relevant_posts):
        """Generate email report for relevant posts"""
        if not relevant_posts:
            return "No relevant Nextdoor posts found."

        # Get search term and day from first post (all posts should have same search_term now)
        search_term = relevant_posts[0].get('search_term', 'unknown')
        day_of_week = datetime.now().strftime('%A')

        report_lines = []
        report_lines.append("🏠 NEXTDOOR SEARCH RESULTS")
        report_lines.append("=" * 50)
        report_lines.append(f"Search: \"{search_term}\"")
        report_lines.append(f"Day: {day_of_week}")
        report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append("=" * 50)
        report_lines.append("")

        # Sort posts alphabetically by author
        sorted_posts = sorted(relevant_posts, key=lambda x: x.get('author', 'Unknown'))

        report_lines.append("🏠 SERVICE OPPORTUNITIES:")
        report_lines.append("")

        for i, post in enumerate(sorted_posts, 1):
            analysis = post.get('analysis', {})

            report_lines.append(f"{i}. {post['author']} - {analysis.get('service_type', 'general').replace('_', ' ').title()}")
            report_lines.append(f"   📖 Post: {post['text'][:200]}{'...' if len(post['text']) > 200 else ''}")
            if post.get('url'):
                report_lines.append(f"   🔗 Link: {post['url']}")
            report_lines.append("   " + "-" * 50)
            report_lines.append("")

        report_lines.append("🤖 Generated by Bulqit Nextdoor Monitor")
        report_lines.append("=" * 50)

        return "\n".join(report_lines)

    def send_email_report(self, relevant_posts, all_posts=None):
        """Send email report if there are relevant posts"""
        if not relevant_posts:
            print("📧 No relevant posts found - skipping email")
            return False

        report_content = self.generate_report(relevant_posts)

        # Get search term and day for subject
        search_term = relevant_posts[0].get('search_term', 'unknown') if relevant_posts else 'unknown'
        day_of_week = datetime.now().strftime('%A')

        subject = f"🏠 Nextdoor - {day_of_week} ({search_term}) - {len(relevant_posts)} Posts - {datetime.now().strftime('%Y-%m-%d')}"

        success = self.email_sender._send_with_custom_subject(
            report_content,
            ["fxs@bulqit.com", "tjv@bulqit.com"],
            subject,
            json_attachment=all_posts
        )

        if success:
            print(f"✅ Email report sent with {len(relevant_posts)} opportunities")
        else:
            print("❌ Failed to send email report")

        return success

    def send_2fa_notification_with_gist(self, gist_url):
        """Send notification that 2FA was triggered with GitHub Gist instructions"""
        report_content = f"""
🚨 NEXTDOOR LOGIN ISSUE - 2FA REQUIRED (GIST POLLING ACTIVE)

Nextdoor is requesting a verification code during login.

🔄 The scanner created a private GitHub Gist and is waiting for your 2FA code!

INSTRUCTIONS:
1. Check your email/phone for the Nextdoor verification code
2. Click this link: {gist_url}
3. Click "Edit" on the gist
4. Replace "ENTER_2FA_CODE_HERE" with your 6-digit verification code
5. Click "Update public gist" to save

⏰ The scanner will check for your code every 30 seconds for the next 3 minutes.
🗑️ The gist will be automatically deleted after use.

🚀 LIVE MODE: Will attempt actual 2FA login after receiving code.

Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

🤖 Generated by Bulqit Nextdoor Monitor
        """

        subject = f"🚨 Nextdoor 2FA - CODE NEEDED VIA GIST - {datetime.now().strftime('%Y-%m-%d')}"

        success = self.email_sender._send_with_custom_subject(
            report_content,
            ["fxs@bulqit.com"],
            subject
        )

        if success:
            print("✅ 2FA polling notification email sent")
        else:
            print("❌ Failed to send 2FA polling notification email")

        return success

class NextdoorScanner:
    def __init__(self):
        self.driver = None
        self.wait = None
        self.service_opportunities = []
        self.groq_client = BulqitGroqClient()
        self.email_sender = EmailSender()
        self.groq_filter = NextdoorGroqFilter(self.groq_client, self.email_sender)
        self.github_token = os.getenv('GIST_TOKEN')
        self.current_gist_id = None

    def _setup_headless_driver(self):
        """Setup headless Chrome driver for Nextdoor"""
        print("🔧 Setting up Chrome for GitHub Actions environment")

        chrome_options = Options()

        # Set Chrome binary location for GitHub Actions
        if os.path.exists('/usr/bin/chromium-browser'):
            chrome_options.binary_location = '/usr/bin/chromium-browser'
        elif os.path.exists('/usr/bin/google-chrome'):
            chrome_options.binary_location = '/usr/bin/google-chrome'

        # Visible mode for testing
        # chrome_options.add_argument("--headless")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--remote-debugging-port=0")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-plugins")
        chrome_options.add_argument("--disable-background-networking")
        chrome_options.add_argument("--disable-default-apps")
        chrome_options.add_argument("--disable-sync")
        chrome_options.add_argument("--no-first-run")
        chrome_options.add_argument("--no-default-browser-check")
        chrome_options.add_argument("--disable-background-timer-throttling")
        chrome_options.add_argument("--disable-renderer-backgrounding")
        chrome_options.add_argument("--disable-backgrounding-occluded-windows")
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--disable-features=VizDisplayCompositor")
        chrome_options.add_argument("--memory-pressure-off")
        chrome_options.add_argument("--max_old_space_size=4096")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        # Block notifications
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_experimental_option("prefs", {
            "profile.default_content_setting_values.notifications": 2
        })

        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            # Set viewport size for headless mode
            self.driver.set_window_size(1920, 1080)

            # Clear all cookies and data
            self.driver.get("chrome://settings/clearBrowserData")
            time.sleep(2)
            self.driver.delete_all_cookies()

            self.wait = WebDriverWait(self.driver, 20)
            print("✅ Chrome driver initialized for Nextdoor (cookies cleared)")
            return True
        except Exception as e:
            print(f"❌ Failed to initialize Chrome driver: {str(e)}")
            return False

    def _type_letter_by_letter(self, element, text):
        """Type text letter by letter with human-like delays"""
        element.clear()
        for char in text:
            element.send_keys(char)
            time.sleep(random.uniform(0.1, 0.3))

    def _login_to_nextdoor(self):
        """Login to Nextdoor automatically"""
        try:
            print("🌍 Navigating to Nextdoor news feed...")
            self.driver.get("https://nextdoor.com/news_feed/")

            # Wait for page to load
            time.sleep(5)

            print(f"📍 Current URL: {self.driver.current_url}")

            # Check if already logged in (successful access to news feed)
            if "news_feed" in self.driver.current_url and "login" not in self.driver.current_url:
                print("✅ Already logged in! Skipping login process.")
            else:
                # Handle login process
                if "login" in self.driver.current_url:
                    print(f"🔐 Redirected to login page: {self.driver.current_url}")
                    print("🔑 Need to login to access news feed - proceeding with login...")
                else:
                    print("🌍 Navigating to login page...")
                    self.driver.get("https://nextdoor.com/login/")
                    time.sleep(3)
                    print(f"📍 Login page URL: {self.driver.current_url}")

                # Find and fill email field
                email_selectors = [
                    'input[type="email"]',
                    'input[name="email"]',
                    '#email',
                    'input[placeholder*="email"]'
                ]

                email_field = None
                for selector in email_selectors:
                    try:
                        email_field = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                        print(f"✅ Found email field with selector: {selector}")
                        break
                    except:
                        continue

                if not email_field:
                    print("❌ Could not find email field")
                    return False

                print("📧 Typing email letter by letter...")
                self._type_letter_by_letter(email_field, "fxs@bulqit.com")

                # Human-like delay
                time.sleep(random.uniform(1, 2))

                # Find and fill password field
                password_selectors = [
                    'input[type="password"]',
                    'input[name="password"]',
                    '#password',
                    'input[placeholder*="password"]'
                ]

                password_field = None
                for selector in password_selectors:
                    try:
                        password_field = self.driver.find_element(By.CSS_SELECTOR, selector)
                        print(f"✅ Found password field with selector: {selector}")
                        break
                    except:
                        continue

                if not password_field:
                    print("❌ Could not find password field")
                    return False

                print("🔒 Typing password letter by letter...")
                self._type_letter_by_letter(password_field, "@Bulqit123!")

                # Another delay
                time.sleep(random.uniform(1, 2))

                # Find and click login button
                login_selectors = [
                    'button[type="submit"]',
                    'input[type="submit"]',
                    'button:contains("Log in")',
                    'button:contains("Sign in")',
                    '[data-testid="login-button"]'
                ]

                login_button = None
                for selector in login_selectors:
                    try:
                        login_button = self.driver.find_element(By.CSS_SELECTOR, selector)
                        print(f"✅ Found login button with selector: {selector}")
                        break
                    except:
                        continue

                if not login_button:
                    print("❌ Could not find login button")
                    return False

                print("🔐 Clicking login button...")
                login_button.click()

                # Wait for login to process
                time.sleep(8)

                # Check for 2FA requirement
                try:
                    needs_2fa = self._check_for_2fa()
                except Exception as e:
                    print(f"❌ Error checking for 2FA: {str(e)}")
                    return False

                if needs_2fa:
                    print("🚨 2FA verification required - capturing HTML for analysis")

                    # Save the 2FA page HTML for debugging
                    try:
                        with open('2fa_page.html', 'w', encoding='utf-8') as f:
                            f.write(self.driver.page_source)
                        print("✅ Saved 2FA page HTML as 2fa_page.html")
                    except Exception as e:
                        print(f"⚠️ Could not save HTML: {str(e)}")

                    # Detect if we're running in GitHub Actions (automated) or locally (manual)
                    is_github_actions = os.getenv('GITHUB_ACTIONS') == 'true'

                    if is_github_actions and self.github_token:
                        print("🚨 Attempting automated 2FA via GitHub Gist polling")
                        # Wait for 2FA code via GitHub Gist polling
                        two_fa_code = self._wait_for_2fa_code()

                        if two_fa_code:
                            print("✅ 2FA code received - attempting to continue login")
                            if self._enter_2fa_code(two_fa_code):
                                print("✅ 2FA verification successful - continuing scan")
                                time.sleep(5)  # Wait for login to complete
                            else:
                                print("❌ 2FA verification failed - stopping scan")
                                return False
                        else:
                            print("❌ 2FA code not received within timeout - stopping scan")
                            return False
                    else:
                        print("🚨 Running locally - using manual 2FA handling")
                        print("👁️ Browser window should be visible - please complete 2FA manually")
                        print("⏰ Waiting 60 seconds for you to complete 2FA...")
                        # Wait for manual 2FA completion
                        for i in range(60):
                            time.sleep(1)
                            current_url = self.driver.current_url.lower()
                            if "login" not in current_url:
                                print("✅ 2FA completed successfully!")
                                break
                            if i % 10 == 0:
                                print(f"⏳ Waiting for 2FA completion... {60-i}s remaining")
                        # Check if 2FA was successful
                        if "login" in self.driver.current_url.lower():
                            print("❌ 2FA not completed within 60 seconds")
                            return False
                        else:
                            print("✅ Successfully logged in after 2FA")

            print(f"📍 After login URL: {self.driver.current_url}")

            # Weekly rotation: One search term per day to avoid shadowban
            # Map day of week to search term
            search_schedule = {
                0: "pool",              # Monday
                1: "window",            # Tuesday
                2: "bin",               # Wednesday
                3: "lawn",              # Thursday
                4: "gardener",          # Friday
                5: "pest control",      # Saturday
                6: "pressure washing"   # Sunday
            }

            # Get today's search term based on day of week
            today_weekday = datetime.now().weekday()  # 0=Monday, 6=Sunday
            today_term = search_schedule[today_weekday]

            print(f"\n📅 Today is {datetime.now().strftime('%A')} - searching for: '{today_term}'")
            print(f"🔍 Single search strategy: One term per day to avoid shadowban")

            all_posts = []

            # Only search today's term (no loop)
            term = today_term
            print(f"\n🔍 Search 1/1: '{term}'")

            is_first_search = True
            if self._search_for_term(term, is_first_search):
                print("✅ Search completed")

                # Anti-detection: random delay after search
                time.sleep(random.uniform(2, 4))

                # Collect posts for this search term
                posts = self._scroll_and_collect_posts()
                if posts:
                    # Tag posts with search term
                    for post in posts:
                        post['search_term'] = term
                    all_posts.extend(posts)
                    print(f"✅ Found {len(posts)} posts for '{term}'")
                else:
                    print(f"⚠️ No posts found for '{term}'")
                    # Send alert if no posts found (possible shadowban)
                    alert_message = f"""
⚠️ ZERO POSTS ALERT - Nextdoor Scanner

The Nextdoor scanner found 0 posts for today's search.

Details:
- Day: {datetime.now().strftime('%A')}
- Search term: '{term}'
- Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

This could indicate:
1. No posts matching the search this week
2. Possible shadowban
3. Technical issue

If this happens multiple days in a row, consider checking manually.

🤖 Generated by Bulqit Nextdoor Monitor
                    """

                    self.email_sender._send_with_custom_subject(
                        alert_message,
                        ["fxs@bulqit.com"],
                        f"⚠️ Nextdoor Zero Posts - {term} - {datetime.now().strftime('%Y-%m-%d')}"
                    )
            else:
                print("❌ Search failed")

            # Remove duplicates across all searches
            unique_posts = []
            seen_texts = set()

            for post in all_posts:
                text_key = post['text'][:50].lower().strip()
                if text_key not in seen_texts:
                    unique_posts.append(post)
                    seen_texts.add(text_key)

            print(f"\n📊 Total unique posts across all searches: {len(unique_posts)}")

            if unique_posts:
                self._save_results(unique_posts)
                print(f"✅ Saved {len(unique_posts)} unique posts")

                # Filter posts through Groq for relevance
                print(f"🤖 Analyzing posts with Groq for Bulqit relevance...")
                relevant_posts = self.groq_filter.filter_posts(unique_posts)

                if relevant_posts:
                    print(f"📧 Sending email report with {len(relevant_posts)} relevant opportunities")
                    self.groq_filter.send_email_report(relevant_posts, unique_posts)
                else:
                    print("📧 No relevant posts found - no email sent")
            else:
                print("❌ No posts found")

            return True

        except Exception as e:
            print(f"❌ Error during login: {str(e)}")
            return False

    def _check_for_2fa(self):
        """Check if 2FA verification is required"""
        try:
            print("🔍 Checking for 2FA requirement...")
            current_url = self.driver.current_url.lower()
            print(f"📍 Current URL: {current_url}")

            if "login" in current_url:
                print("🚨 2FA detected: 'login' found in URL")
                return True

            print("✅ No 2FA requirement detected")
            return False

        except Exception as e:
            print(f"⚠️ Error checking for 2FA: {str(e)}")
            return False

    def _create_2fa_gist(self):
        """Create a private GitHub Gist for 2FA code input"""
        if not self.github_token:
            print("❌ GitHub token not found for Gist creation")
            return None

        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')
            gist_data = {
                "description": f"Nextdoor 2FA Code Input - {timestamp}",
                "public": False,
                "files": {
                    "nextdoor_2fa_code.txt": {
                        "content": f"""ENTER_2FA_CODE_HERE

Instructions:
1. Replace "ENTER_2FA_CODE_HERE" above with your 6-digit Nextdoor verification code
2. Save this gist
3. The scanner will automatically detect your code and continue

Created: {timestamp}
This gist will be automatically deleted after use.
"""
                    }
                }
            }

            headers = {
                'Authorization': f'token {self.github_token}',
                'Accept': 'application/vnd.github.v3+json'
            }

            response = requests.post('https://api.github.com/gists',
                                   json=gist_data, headers=headers)

            if response.status_code == 201:
                gist_info = response.json()
                self.current_gist_id = gist_info['id']
                gist_url = gist_info['html_url']
                print(f"✅ Created private gist: {gist_url}")
                return gist_url
            else:
                print(f"❌ Failed to create gist: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            print(f"❌ Error creating gist: {str(e)}")
            return None

    def _poll_gist_for_code(self):
        """Poll the GitHub Gist for 2FA code updates"""
        if not self.github_token or not self.current_gist_id:
            print("❌ Missing GitHub token or gist ID")
            return None

        try:
            headers = {
                'Authorization': f'token {self.github_token}',
                'Accept': 'application/vnd.github.v3+json'
            }

            url = f'https://api.github.com/gists/{self.current_gist_id}'
            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                gist_data = response.json()
                file_content = gist_data['files']['nextdoor_2fa_code.txt']['content']

                print(f"📖 Gist content preview: '{file_content[:50]}...'")

                # Look for 6-digit code
                lines = file_content.split('\n')
                for line in lines:
                    line = line.strip()
                    if line and line.isdigit() and len(line) == 6:
                        print(f"✅ Found 2FA code in gist: {line}")
                        return line
                    elif line and line != 'ENTER_2FA_CODE_HERE' and not line.startswith('Instructions:'):
                        # Extract digits from the line
                        digits = ''.join(c for c in line if c.isdigit())
                        if len(digits) == 6:
                            print(f"✅ Found 2FA code in gist: {digits}")
                            return digits

                return None
            else:
                print(f"❌ Failed to read gist: {response.status_code}")
                return None

        except Exception as e:
            print(f"❌ Error polling gist: {str(e)}")
            return None

    def _delete_2fa_gist(self):
        """Delete the 2FA gist after use"""
        if not self.github_token or not self.current_gist_id:
            return

        try:
            headers = {
                'Authorization': f'token {self.github_token}',
                'Accept': 'application/vnd.github.v3+json'
            }

            url = f'https://api.github.com/gists/{self.current_gist_id}'
            response = requests.delete(url, headers=headers)

            if response.status_code == 204:
                print(f"🗑️ Deleted 2FA gist: {self.current_gist_id}")
            else:
                print(f"⚠️ Failed to delete gist: {response.status_code}")

            self.current_gist_id = None

        except Exception as e:
            print(f"⚠️ Error deleting gist: {str(e)}")

    def _wait_for_2fa_code(self):
        """Wait for 2FA code to be provided via GitHub Gist polling"""
        try:
            print("🔄 Creating GitHub Gist for 2FA code input...")

            # Create private gist
            gist_url = self._create_2fa_gist()
            if not gist_url:
                print("❌ Failed to create gist - stopping")
                return None

            # Send notification email with gist URL
            self.groq_filter.send_2fa_notification_with_gist(gist_url)

            # Poll for 2FA code for up to 3 minutes (180 seconds)
            max_attempts = 6  # 6 attempts * 30 seconds = 3 minutes
            attempt = 0

            while attempt < max_attempts:
                code = self._poll_gist_for_code()
                if code:
                    print(f"✅ 2FA code received from gist - cleaning up")
                    self._delete_2fa_gist()
                    return code

                attempt += 1
                remaining_time = (max_attempts - attempt) * 30
                print(f"⏳ Attempt {attempt}/{max_attempts} - Waiting for 2FA code... ({remaining_time}s remaining)")
                time.sleep(30)

            print("❌ Timeout waiting for 2FA code (3 minutes)")
            self._delete_2fa_gist()
            return None

        except Exception as e:
            print(f"⚠️ Error in 2FA gist polling: {str(e)}")
            self._delete_2fa_gist()
            return None

    def _enter_2fa_code(self, code):
        """Enter the 2FA code into the form"""
        try:
            print(f"🔐 Entering 2FA code: {code}")

            # Find 2FA input fields
            try:
                input_elements = self.driver.find_elements(By.CSS_SELECTOR, 'input[id^="_r"][id$="_"]')
                input_ids = [elem.get_attribute('id') for elem in input_elements if elem.is_displayed()]
                input_ids.sort()
                print(f"📝 Found {len(input_ids)} 2FA input fields: {input_ids}")
            except Exception as e:
                print(f"⚠️ Error finding input fields, using fallback: {str(e)}")
                input_ids = ['_rd_', '_re_', '_rf_', '_rg_', '_rh_', '_ri_']

            if len(code) != 6:
                print(f"❌ 2FA code must be 6 digits, got {len(code)}: {code}")
                return False

            # Enter each digit into its respective field
            for i, digit in enumerate(code):
                try:
                    input_field = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.ID, input_ids[i]))
                    )
                    input_field.clear()
                    input_field.send_keys(digit)
                    print(f"✅ Entered digit {digit} into field {input_ids[i]}")
                    time.sleep(0.2)
                except Exception as e:
                    print(f"❌ Could not enter digit {digit} into field {input_ids[i]}: {str(e)}")
                    return False

            print("✅ All 6 digits entered successfully")
            time.sleep(3)

            # Check if login was successful
            try:
                current_url = self.driver.current_url
                print(f"📍 URL after entering code: {current_url}")

                if "/login/" not in current_url:
                    print("✅ Login successful - moved past login page")
                    return True

            except Exception as e:
                print(f"⚠️ Could not check URL: {str(e)}")

            return True

        except Exception as e:
            print(f"⚠️ Error entering 2FA code: {str(e)}")
            return False

    def _search_for_term(self, search_term, is_first_search=False):
        """Search for a specific term in Nextdoor search box"""
        try:
            print(f"🔍 Searching for: {search_term}")
            time.sleep(3)

            # Try different search box selectors
            search_selectors = [
                '#search-input-field',
                'input[aria-label="Search Nextdoor"]',
                'input[placeholder*="Search"]',
                'input[placeholder*="search"]',
                'input[type="search"]',
                '[data-testid="search-input"]',
                '.search-input',
                'input[name="search"]',
                '#search',
                'input[aria-label*="Search"]'
            ]

            search_box = None
            for selector in search_selectors:
                try:
                    search_box = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                    print(f"✅ Found search box with selector: {selector}")
                    break
                except:
                    continue

            if not search_box:
                print("❌ Could not find search box")
                return False

            # Click to focus and type search term
            search_box.click()
            time.sleep(1)

            print(f"⌨️ Typing '{search_term}' letter by letter...")
            self._type_letter_by_letter(search_box, search_term)
            time.sleep(2)

            # Find and click search button or press Enter
            search_button_selectors = [
                'button[type="submit"]',
                'button[aria-label*="Search"]',
                '[data-testid="search-button"]',
                '.search-button',
                'button:contains("Search")'
            ]

            search_clicked = False
            for selector in search_button_selectors:
                try:
                    search_button = self.driver.find_element(By.CSS_SELECTOR, selector)
                    print(f"✅ Found search button with selector: {selector}")
                    search_button.click()
                    search_clicked = True
                    break
                except:
                    continue

            if not search_clicked:
                print("🔍 No search button found, pressing Enter...")
                search_box.send_keys('\n')

            time.sleep(5)
            print(f"📍 After search URL: {self.driver.current_url}")

            # Only apply filters on the first search
            if is_first_search:
                print("🔧 First search - applying Posts tab and This week filter")

                if self._click_posts_tab():
                    print("✅ Posts tab clicked")
                else:
                    print("❌ Failed to click Posts tab")

                if self._set_time_filter_to_this_week():
                    print("✅ Time filter set to This week")
                else:
                    print("❌ Failed to set time filter")
            else:
                print("🔧 Subsequent search - skipping Posts tab and This week filter (already set)")

            return True

        except Exception as e:
            print(f"❌ Error during search: {str(e)}")
            return False

    def _click_posts_tab(self):
        """Click the Posts tab in search results"""
        try:
            print("📝 Looking for Posts tab...")

            posts_tab_selectors = [
                '[data-testid="tab-posts"]',
                '#id-209-posts',
                'a[role="tab"][aria-controls*="posts-panel"]',
                'a:contains("Posts")',
                '[href*="/search/posts/"]'
            ]

            for selector in posts_tab_selectors:
                try:
                    posts_tab = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
                    print(f"✅ Found Posts tab with selector: {selector}")
                    posts_tab.click()
                    time.sleep(3)
                    print(f"📍 After Posts click URL: {self.driver.current_url}")
                    return True
                except:
                    continue

            print("❌ Could not find Posts tab")
            return False

        except Exception as e:
            print(f"❌ Error clicking Posts tab: {str(e)}")
            return False

    def _set_time_filter_to_this_week(self):
        """Click time filter button and select This week"""
        try:
            print("📅 Looking for time filter button...")

            # Use JavaScript to find and click the time filter
            time_filter_found = self.driver.execute_script("""
                var elements = document.querySelectorAll('span');
                for (var i = 0; i < elements.length; i++) {
                    if (elements[i].textContent.includes('All Time')) {
                        var button = elements[i].closest('.BaseButton__emelwr2') || elements[i].closest('div[data-part="button"]');
                        if (button) {
                            button.click();
                            return true;
                        }
                    }
                }
                return false;
            """)

            if not time_filter_found:
                print("❌ Could not find time filter button")
                return False

            print("✅ Found and clicked time filter button")
            time.sleep(2)

            # Now look for "This week" option in the dropdown
            print("📅 Looking for 'This week' option...")

            this_week_found = self.driver.execute_script("""
                var elements = document.querySelectorAll('span, div, button, li');
                for (var i = 0; i < elements.length; i++) {
                    if (elements[i].textContent.trim() === 'This week') {
                        elements[i].click();
                        return true;
                    }
                }
                return false;
            """)

            if this_week_found:
                print("✅ Selected 'This week' option")
                time.sleep(2)
                return True
            else:
                print("❌ Could not find 'This week' option")
                return False

        except Exception as e:
            print(f"❌ Error setting time filter: {str(e)}")
            return False

    def _detect_post_selector_with_ai(self, html_source):
        """Use AI to detect the correct CSS selector for post containers"""
        try:
            # Extract a snippet of HTML to analyze (first 50KB to avoid token limits)
            html_snippet = html_source[:50000]

            prompt = f"""Analyze this Nextdoor search results page HTML and identify the CSS selector for individual post containers.

Look for repeating div elements that contain:
- Author name/avatar
- Post text content
- Timestamp
- Comment count

Return ONLY the CSS selector in one of these formats:
- Class selector: .classname
- Attribute selector: [attribute-name="value"]

HTML snippet:
{html_snippet}

CSS Selector:"""

            response = self.groq_client.client.chat.completions.create(
                model=self.groq_client.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=100
            )

            selector = response.choices[0].message.content.strip()

            # Validate it looks like a selector
            if selector.startswith('.') or selector.startswith('['):
                return selector
            else:
                print(f"⚠️ AI returned invalid selector: {selector}")
                return None

        except Exception as e:
            print(f"❌ Error detecting selector with AI: {e}")
            return None

    def _extract_nextdoor_posts(self):
        """Extract main posts from Nextdoor page"""
        try:
            print("📝 Extracting posts from page...")
            time.sleep(3)

            page_source = self.driver.page_source

            # Save full HTML for debugging
            try:
                with open('search_page_full.html', 'w', encoding='utf-8') as f:
                    f.write(page_source)
                print("💾 Saved full page HTML to search_page_full.html")
            except Exception as e:
                print(f"⚠️ Could not save HTML: {str(e)}")

            soup = BeautifulSoup(page_source, "html.parser")
            posts_data = []

            # Look for main content area
            main_content = soup.find('div', {'id': 'main_content'})
            if not main_content:
                print("❌ Could not find main content area")
                return []

            # Find all post containers - try multiple selectors for reliability
            # Method 1: Try data-testid (most stable)
            post_containers = main_content.find_all('div', attrs={'data-testid': lambda x: x and 'dwell-tracker-searchFeedItem' in x})

            # Method 2: Fallback to class name if data-testid doesn't work
            if not post_containers:
                post_containers = main_content.find_all('div', class_='_7uk7470')

            # Method 3: Last resort - look for divs with specific structure
            if not post_containers:
                post_containers = main_content.find_all('div', attrs={'data-v3-view-type': 'V3Wrapper'})

            # Method 4: AI-powered selector discovery if nothing found
            if not post_containers:
                print("🤖 No posts found with known selectors - using AI to detect new selector...")
                detected_selector = self._detect_post_selector_with_ai(page_source)
                if detected_selector:
                    print(f"✅ AI detected selector: {detected_selector}")
                    # Try the AI-detected selector
                    try:
                        if detected_selector.startswith('.'):
                            # Class selector
                            post_containers = main_content.find_all('div', class_=detected_selector[1:])
                        elif detected_selector.startswith('['):
                            # Attribute selector like [data-testid="..."]
                            import re
                            attr_match = re.match(r'\[([^=]+)="([^"]+)"\]', detected_selector)
                            if attr_match:
                                attr_name, attr_value = attr_match.groups()
                                post_containers = main_content.find_all('div', attrs={attr_name: attr_value})
                    except Exception as e:
                        print(f"⚠️ Error using AI-detected selector: {e}")

            print(f"🔍 Found {len(post_containers)} potential post containers")

            # Save all container HTML to debug file
            debug_content = []
            debug_content.append(f"=== FOUND {len(post_containers)} POST CONTAINERS ===\n")

            for i, container in enumerate(post_containers):
                debug_content.append(f"\n--- CONTAINER {i+1} ---")
                debug_content.append(f"Outer HTML: {str(container)[:1000]}...")  # First 1000 chars
                debug_content.append(f"Text content: {container.get_text()[:500]}...")  # First 500 chars
                debug_content.append(f"Classes: {container.get('class', [])}")
                debug_content.append("-" * 80)

            # Write debug file
            try:
                with open('post_containers_debug.txt', 'w', encoding='utf-8') as f:
                    f.write('\n'.join(debug_content))
                print(f"📄 Saved container debug info to post_containers_debug.txt")
            except Exception as e:
                print(f"⚠️ Could not save debug file: {str(e)}")

            for i, container in enumerate(post_containers):
                try:
                    # Extract post URL from the link
                    post_url = ""
                    post_link = container.find('a', class_='BaseLink__kjvg670')
                    if post_link and post_link.get('href'):
                        post_url = "https://nextdoor.com" + post_link.get('href')

                    # Get the full text content and parse author from it
                    full_text = container.get_text(strip=True)

                    # Skip traffic alerts and other system posts
                    if "Traffic Alerts" in full_text or not full_text:
                        continue

                    # Extract author name and post text from format: "AuthorNameLocation, CA · time agoPost content"
                    author_name = ""
                    post_text = ""

                    # Split by ' · ' to separate author/location from time and content
                    parts = full_text.split(' · ')

                    if len(parts) >= 2:
                        # First part: "AuthorNameLocation, CA"
                        author_location = parts[0].strip()

                        # Extract author name (everything before location)
                        if ', CA' in author_location:
                            author_name = author_location.split(', CA')[0].strip()
                        else:
                            # Handle cases like "Ever hernandezLos Angeles" - find where location starts
                            import re
                            # Look for common LA area locations (longer names first to avoid partial matches)
                            locations = ['West Studio City', 'Studio City', 'Sherman Oaks', 'Panorama City', 'Mandeville Canyon',
                                       'Cahuenga Pass', 'Brentwood Place', 'West Hills', 'North Hollywood', 'Valley Village',
                                       'Los Angeles', 'West LA', 'Encino', 'Tarzana', 'Burbank', 'Brentwood', 'Palisades',
                                       'The Highlands', 'Glendale', 'Pasadena', 'Beverly Hills', 'WeHo', 'Kenter', 'Central']

                            author_name = author_location
                            for location in locations:
                                if location in author_location:
                                    # Find the exact position where location starts
                                    loc_index = author_location.find(location)
                                    if loc_index > 0:
                                        author_name = author_location[:loc_index].strip()
                                        break

                            # Clean up author name - remove any trailing location fragments
                            author_name = re.sub(r'\s*(CA|California)\s*$', '', author_name).strip()

                        # Second part onwards: "time agoPost content"
                        remaining = ' · '.join(parts[1:])

                        # Find where the actual post content starts (after "ago")
                        if ' ago' in remaining:
                            ago_split = remaining.split(' ago', 1)
                            if len(ago_split) == 2:
                                post_text = ago_split[1].strip()
                        else:
                            # Fallback
                            post_text = remaining

                        # Clean up post text - remove replies/responses
                        if post_text:
                            # Look for patterns that indicate a reply has been concatenated
                            import re

                            # Multiple patterns for detecting replies:
                            # Pattern 1: Number followed by name and location
                            reply_patterns = [
                                r'(\d+)([A-Z][a-z]*\s*[A-Z][a-z]*.*?(?:Los Angeles|Studio City|Sherman Oaks|Encino|Burbank|Panorama City|Mandeville|Cahuenga|Brentwood|Palisades|Highlands|West|Central|Kenter|WeHo|Glendale))',
                                # Pattern 2: Just a number followed by capital letter (likely a reply count + name)
                                r'(\d{2,})([A-Z][A-Z][a-z])',
                                # Pattern 3: Time stamp followed by name
                                r'(\d+\s*hr?\s*ago)([A-Z][a-z]+ [A-Z])',
                            ]

                            for pattern in reply_patterns:
                                match = re.search(pattern, post_text)
                                if match:
                                    # Extract just the main post (everything before the reply)
                                    post_text = post_text[:match.start()].strip()
                                    break

                    else:
                        # No proper format found, use whole text
                        post_text = full_text

                    # Clean up post text - remove time stamps and replies
                    if post_text:
                        # Remove reply indicators and numbers
                        import re
                        post_text = re.sub(r'^\d+\s*', '', post_text)  # Remove leading numbers
                        post_text = re.sub(r'\d+\s*$', '', post_text)  # Remove trailing numbers
                        post_text = post_text.strip()

                    # Skip if missing essential data or if it's too short
                    if not author_name or not post_text or len(post_text) < 20:
                        continue

                    # Only process substantial main posts
                    if (post_text and len(post_text) > 30 and
                        author_name and author_name != "Unknown"):

                        # Additional filtering for main posts
                        is_main_post = True

                        if len(post_text) < 40:
                            is_main_post = False

                        reply_indicators = ['@', 'Reply to', 'Thanks', 'Thank you', 'Yes', 'No', 'Agree', 'Same here']
                        if any(indicator in post_text[:30] for indicator in reply_indicators):
                            is_main_post = False

                        if is_main_post:
                            post_data = {
                                'text': post_text,
                                'author': author_name,
                                'url': post_url,
                                'search_term': "",  # Will be set later
                                'debug_full_text': full_text[:200]  # For debugging
                            }

                            posts_data.append(post_data)
                            print(f"✅ Main Post {len(posts_data)}: {post_text[:60]}... (by {author_name})")
                            if post_url:
                                print(f"   🔗 URL: {post_url}")
                        else:
                            print(f"🔄 Skipped reply: {post_text[:30]}... (by {author_name})")

                except Exception as e:
                    print(f"⚠️ Error processing container {i+1}: {str(e)}")
                    continue

            # Remove duplicates
            unique_posts = []
            seen_texts = set()

            for post in posts_data:
                text_key = post['text'][:50].lower().strip()
                if text_key not in seen_texts:
                    unique_posts.append(post)
                    seen_texts.add(text_key)
                else:
                    print(f"🔄 Skipped duplicate: {post['text'][:30]}...")

            print(f"📝 Successfully extracted {len(unique_posts)} unique main posts")

            # Save extracted posts to debug file
            try:
                debug_extracted = []
                debug_extracted.append(f"=== EXTRACTED {len(unique_posts)} POSTS ===\n")

                for i, post in enumerate(unique_posts):
                    debug_extracted.append(f"\n--- EXTRACTED POST {i+1} ---")
                    debug_extracted.append(f"Author: {post['author']}")
                    debug_extracted.append(f"Text: {post['text']}")
                    debug_extracted.append(f"URL: {post['url']}")
                    debug_extracted.append(f"Debug Full Text: {post.get('debug_full_text', 'N/A')}")
                    debug_extracted.append("-" * 80)

                with open('extracted_posts_debug.txt', 'w', encoding='utf-8') as f:
                    f.write('\n'.join(debug_extracted))
                print(f"📄 Saved extracted posts to extracted_posts_debug.txt")
            except Exception as e:
                print(f"⚠️ Could not save extracted debug file: {str(e)}")

            return unique_posts

        except Exception as e:
            print(f"❌ Error extracting posts: {str(e)}")
            return []

    def _handle_popups(self):
        """Handle Nextdoor popups and overlays"""
        try:
            popup_closed = self.driver.execute_script("""
                var popupsFound = 0;

                var closeSelectors = [
                    '[aria-label="Close"]',
                    'button[aria-label="Close"]',
                    '.close-button',
                    '[data-testid="close-button"]',
                    '.modal-close',
                    '[aria-label="Dismiss"]'
                ];

                closeSelectors.forEach(function(selector) {
                    var elements = document.querySelectorAll(selector);
                    elements.forEach(function(element) {
                        if (element.offsetParent !== null) {
                            try {
                                element.click();
                                popupsFound++;
                            } catch (e) {}
                        }
                    });
                });

                return popupsFound;
            """)

            if popup_closed > 0:
                print(f"✅ Closed {popup_closed} popups")
                time.sleep(2)

        except Exception as e:
            print(f"⚠️ Error handling popups: {str(e)}")

    def _scroll_and_collect_posts(self, max_scrolls=20):
        """Scroll through Nextdoor feed until bottom is reached"""
        all_posts = []
        scroll_count = 0
        no_new_posts_count = 0

        print(f"📜 Starting to scroll and collect posts (max {max_scrolls} scrolls)")

        while scroll_count < max_scrolls:
            scroll_count += 1
            print(f"📍 Scroll {scroll_count}")

            # Get current page height before scrolling
            current_height = self.driver.execute_script("return document.body.scrollHeight")

            # Extract posts from current view
            posts = self._extract_nextdoor_posts()

            # Add new posts (check for duplicates)
            new_posts_added = 0
            for post in posts:
                if not any(existing['text'][:50] == post['text'][:50] for existing in all_posts):
                    post['scroll_found'] = scroll_count
                    all_posts.append(post)
                    new_posts_added += 1

            print(f"📊 Added {new_posts_added} new posts, total: {len(all_posts)}")

            # Track if we're getting new posts
            if new_posts_added == 0:
                no_new_posts_count += 1
            else:
                no_new_posts_count = 0

            # Stop if no new posts for 3 consecutive scrolls
            if no_new_posts_count >= 3:
                print("🔚 No new posts found for 3 scrolls - likely reached bottom")
                break

            # More human-like scrolling behavior
            # Random chance to scroll up first (like reading something above)
            if random.random() < 0.15:  # 15% chance
                scroll_up = random.randint(100, 400)
                self.driver.execute_script(f"window.scrollBy(0, -{scroll_up});")
                time.sleep(random.uniform(0.5, 1.5))

            # Vary scroll amounts much more (humans don't scroll consistently)
            scroll_amount = random.randint(200, 1500)
            self.driver.execute_script(f"window.scrollBy(0, {scroll_amount});")

            # Occasional mid-scroll pause (like reading)
            if random.random() < 0.2:  # 20% chance
                time.sleep(random.uniform(1, 3))

            # More varied wait times
            time.sleep(random.uniform(2, 7))

            # Occasionally hover/click on a post (but don't navigate)
            if random.random() < 0.1:  # 10% chance
                try:
                    # Simulate mouse movement to a random post
                    self.driver.execute_script("""
                        var posts = document.querySelectorAll('[data-block="22"]');
                        if (posts.length > 0) {
                            var randomPost = posts[Math.floor(Math.random() * posts.length)];
                            var event = new MouseEvent('mouseover', {
                                view: window,
                                bubbles: true,
                                cancelable: true
                            });
                            randomPost.dispatchEvent(event);
                        }
                    """)
                    time.sleep(random.uniform(0.5, 2))
                except:
                    pass

            # Check if page height changed
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height == current_height:
                print("📏 Page height unchanged - trying big scroll to load more content...")

                # Try multiple strategies to trigger loading
                for attempt in range(3):
                    print(f"   Attempt {attempt + 1}: Big scroll to trigger loading")

                    # Scroll to absolute bottom
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(2)

                    # Big scroll down to trigger infinite scroll
                    self.driver.execute_script("window.scrollBy(0, 2000);")
                    time.sleep(3)

                    # Check for loading indicators or new content
                    loading_height = self.driver.execute_script("return document.body.scrollHeight")
                    if loading_height > new_height:
                        print(f"✅ Loading triggered! Height increased from {new_height} to {loading_height}")
                        new_height = loading_height
                        break

                    # Try scrolling up slightly then down again (sometimes helps)
                    self.driver.execute_script("window.scrollBy(0, -500);")
                    time.sleep(1)
                    self.driver.execute_script("window.scrollBy(0, 1000);")
                    time.sleep(3)

                    retry_height = self.driver.execute_script("return document.body.scrollHeight")
                    if retry_height > new_height:
                        print(f"✅ Retry scroll worked! Height increased from {new_height} to {retry_height}")
                        new_height = retry_height
                        break

                # Final check after all attempts
                final_height = self.driver.execute_script("return document.body.scrollHeight")
                if final_height == current_height:
                    print("📏 No new content loaded after big scroll attempts")
                    # Don't break immediately - let the no_new_posts_count logic handle it
                else:
                    print(f"📏 Content loaded! Height: {current_height} → {final_height}")
                    current_height = final_height

            # Handle any popups that appear
            self._handle_popups()

        print(f"✅ Scrolling complete after {scroll_count} scrolls")
        return all_posts

    def _save_results(self, posts):
        """Save extracted posts to clean file format"""
        if not posts:
            print("⚠️ No posts to save")
            return

        output_file = f"nextdoor_posts_all_services_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.txt"

        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write("Nextdoor Posts - All Home Services Search\n")
                f.write("=" * 50 + "\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 50 + "\n\n")

                for i, post in enumerate(posts, 1):
                    f.write(f"Post {i}:\n")
                    f.write(f"Author: {post['author']}\n")
                    if post.get('search_term'):
                        f.write(f"Search Term: {post['search_term']}\n")
                    f.write(f"Text: {post['text']}\n")
                    if post.get('url'):
                        f.write(f"URL: {post['url']}\n")
                    f.write("-" * 50 + "\n\n")

                f.write(f"\nTotal posts: {len(posts)}\n")

            print(f"✅ Saved {len(posts)} posts to {output_file}")

        except Exception as e:
            print(f"⚠️ Error saving results: {str(e)}")

    def run_scan(self):
        """Main scanning workflow"""
        print("🚀 Starting Nextdoor Scanner...")
        print("=" * 60)

        if not self._setup_headless_driver():
            return False

        try:
            if not self._login_to_nextdoor():
                print("❌ Failed to login to Nextdoor")
                return False

            print("\n✅ Scan completed successfully!")
            time.sleep(5)
            return True

        except KeyboardInterrupt:
            print("\n👋 Exiting...")
            return True

        except Exception as e:
            print(f"❌ Scan failed: {str(e)}")
            return False

        finally:
            if self.driver:
                try:
                    self.driver.quit()
                except Exception as e:
                    print(f"⚠️ Error closing browser: {str(e)}")
                    import os
                    os.system("pkill -f chrome || true")

def main():
    print("🏠 NEXTDOOR SCANNER - BULQIT SERVICE OPPORTUNITIES")
    print("📋 Complete consolidated version")

    scanner = NextdoorScanner()
    success = scanner.run_scan()

    if success:
        print("\n✅ Nextdoor scan completed!")
    else:
        print("\n❌ Nextdoor scan failed")

if __name__ == "__main__":
    main()
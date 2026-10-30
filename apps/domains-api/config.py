"""Configuration is private to the API. Prices are integer BRL cents, never browser input."""
import json
import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    db: str = field(default_factory=lambda: os.getenv('DOMAINS_DB', '/data/domains.sqlite3'))
    origin: str = field(default_factory=lambda: os.getenv('DOMAINS_ORIGIN', 'https://karenangelis.com').rstrip('/'))
    enabled: bool = field(default_factory=lambda: os.getenv('DOMAINS_SALES_ENABLED') == 'true')
    live: bool = field(default_factory=lambda: os.getenv('DOMAINS_LIVE') == 'true')
    reseller_id: str = field(default_factory=lambda: os.getenv('RESELLERCLUB_ID', ''))
    reseller_key: str = field(default_factory=lambda: os.getenv('RESELLERCLUB_API_KEY', ''))
    mp_token: str = field(default_factory=lambda: os.getenv('MERCADOPAGO_ACCESS_TOKEN', ''))
    mp_secret: str = field(default_factory=lambda: os.getenv('MERCADOPAGO_WEBHOOK_SECRET', ''))
    mp_collector: str = field(default_factory=lambda: os.getenv('MERCADOPAGO_COLLECTOR_ID', ''))
    google_id: str = field(default_factory=lambda: os.getenv('GOOGLE_CLIENT_ID', ''))
    nameservers: list = field(default_factory=lambda: [n.strip() for n in os.getenv('DOMAIN_NAMESERVERS', '').split(',') if n.strip()])
    prices: dict = field(default_factory=lambda: json.loads(os.getenv('DOMAIN_PRICES_JSON', '{}')))
    smtp_host: str = field(default_factory=lambda: os.getenv('DOMAIN_SMTP_HOST', ''))
    smtp_port: int = field(default_factory=lambda: int(os.getenv('DOMAIN_SMTP_PORT', '587')))
    smtp_user: str = field(default_factory=lambda: os.getenv('DOMAIN_SMTP_USER', ''))
    smtp_password: str = field(default_factory=lambda: os.getenv('DOMAIN_SMTP_PASSWORD', ''))
    mail_from: str = field(default_factory=lambda: os.getenv('DOMAIN_MAIL_FROM', ''))

    def __post_init__(self):
        for tld, price in self.prices.items():
            if tld not in {'com', 'net', 'org', 'com.br'}:
                raise ValueError('Unsupported TLD; add its registry requirements before enabling it')
            if set(price) != {'register', 'renew'} or any(type(v) is not int or not 100 <= v <= 1000000 for v in price.values()):
                raise ValueError('Prices must contain register and renew in BRL cents')

    @property
    def search_ready(self):
        return bool(self.reseller_id and self.reseller_key and self.prices)

    @property
    def mail_ready(self):
        return bool(self.smtp_host and self.smtp_user and self.smtp_password and self.mail_from)

    @property
    def sales_ready(self):
        return self.enabled and self.processing_ready

    @property
    def processing_ready(self):
        return bool(self.search_ready and self.mp_token and self.mp_secret
                    and self.mp_collector and len(self.nameservers) >= 2 and self.mail_ready
                    and self.origin.startswith('https://'))

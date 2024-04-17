import base64
import re
from datetime import date, datetime
from io import StringIO

import pandas as pd
import requests
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey


def sign_request_id(req_id: str, private_key: RSAPrivateKey) -> str:
    req_id_bytes = req_id.encode()
    signature = private_key.sign(req_id_bytes, padding.PKCS1v15(), hashes.SHA256())
    signature_base64 = base64.b64encode(signature)
    return signature_base64.decode()


def get_date_and_time(dt_str: str) -> tuple[str, str]:
    dt_obj = datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S.%fZ")
    date_obj = dt_obj.date()
    time_obj = dt_obj.time()
    date_str = date_obj.strftime("%d-%m-%Y")
    time_str = time_obj.strftime("%H:%M:%S")
    return date_str, time_str


class WiseApi:
    UUID_REGEX = r"(^[0-9a-fA-F]{8}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{12}$)"

    def __init__(
        self, api_token: str, private_key_bytes: bytes, use_sandbox: bool = False
    ):
        if not re.match(self.UUID_REGEX, api_token):
            raise ValueError("Invalid API token")
        self.api_token = api_token
        self.private_key = serialization.load_pem_private_key(
            private_key_bytes, password=None, backend=default_backend()
        )
        self.session = requests.Session()
        self.session.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

        if use_sandbox:
            self.url_prefix = "https://api.sandbox.transferwise.tech"
        else:
            self.url_prefix = "https://api.transferwise.com"

    def get_profiles(self) -> list[dict]:
        response = self.session.get(f"{self.url_prefix}/v2/profiles")
        if not response.ok:
            raise ValueError("Failed to get profiles. Check private key.")
        return response.json()

    def get_profile_data(self, selected_account_type: str) -> list[dict]:
        wise_profiles = self.get_profiles()
        profile_data_list = [
            acc for acc in wise_profiles if acc["type"] == selected_account_type
        ]
        if len(profile_data_list) == 0:
            raise ValueError("No business account found.")
        return profile_data_list

    def get_balances(self, profile_id: int, jar: bool = False) -> list[dict]:
        if jar:
            response = self.session.get(
                f"{self.url_prefix}/v4/profiles/{profile_id}/balances?types=SAVINGS",
            )
        else:
            response = self.session.get(
                f"{self.url_prefix}/v4/profiles/{profile_id}/balances?types=STANDARD",
            )
        if not response.ok:
            raise ValueError(f"{response}")
        return response.json()

    def get_eur_balance_dict(
        self, profile_id: int, currency: str, jar: bool = False
    ) -> tuple[dict | list, int | None]:
        all_balances = self.get_balances(profile_id=profile_id, jar=jar)
        eur_balances = [
            balance for balance in all_balances if balance["currency"] == currency
        ]
        if len(eur_balances) > 1:
            raise ValueError(
                "More than one EUR balance found. The first account is displayed."
            )
        if eur_balances:
            eur_balance = eur_balances[0]
            balance_id = eur_balance["id"]
        else:
            eur_balance = eur_balances  # type: ignore
            balance_id = None
        return eur_balance, balance_id

    def get_statement_df(
        self, profile_id: int, balance_id: int, start_date: date, end_date: date
    ) -> pd.DataFrame:
        params = (
            f"intervalStart={start_date.strftime('%Y-%m-%d')}T00:00:00.000Z&"
            f"intervalEnd={end_date.strftime('%Y-%m-%d')}T23:59:59.999Z&type=COMPACT"
        )
        response = self.session.get(
            f"{self.url_prefix}/v1/profiles/{profile_id}/balance-statements"
            f"/{balance_id}/statement.csv",
            params=params,
        )
        if "x-2fa-approval" in response.headers:
            req_id = response.headers["x-2fa-approval"]
            req_signature = sign_request_id(req_id=req_id, private_key=self.private_key)  # type: ignore
            self.session.headers["x-2fa-approval"] = req_id
            self.session.headers["X-Signature"] = req_signature
            response = self.session.get(
                f"{self.url_prefix}/v1/profiles/{profile_id}/balance-statements"
                f"/{balance_id}/statement.csv",
                params=params,
                stream=False,
            )
        if not response.ok:
            raise ValueError(
                f"Failed to get statement (Response: {response}).  Check private key. "
            )
        if "x-2fa-approval" in self.session.headers:
            self.session.headers.pop("x-2fa-approval")
        if "X-Signature" in self.session.headers:
            self.session.headers.pop("X-Signature")
        csv_buffer = StringIO(response.text)
        statement_df = pd.read_csv(csv_buffer, sep=",", header=0)
        statement_df["Payer Name"] = statement_df["Payer Name"].fillna("").astype(str)
        statement_df["Payee Name"] = statement_df["Payee Name"].fillna("").astype(str)
        return statement_df

    def verify_private_key(
        self, profile_id: int, balance_id: int, start_date: date, end_date: date
    ) -> None:
        params = (
            f"intervalStart={start_date.strftime('%Y-%m-%d')}T00:00:00.000Z&"
            f"intervalEnd={end_date.strftime('%Y-%m-%d')}T23:59:59.999Z&type=COMPACT"
        )
        response = self.session.get(
            f"{self.url_prefix}/v1/profiles/{profile_id}/balance-statements"
            f"/{balance_id}/statement.csv",
            params=params,
        )
        if "x-2fa-approval" in response.headers:
            req_id = response.headers["x-2fa-approval"]
            req_signature = sign_request_id(req_id=req_id, private_key=self.private_key)  # type: ignore
            self.session.headers["x-2fa-approval"] = req_id
            self.session.headers["X-Signature"] = req_signature
            response = self.session.get(
                f"{self.url_prefix}/v1/profiles/{profile_id}/balance-statements"
                f"/{balance_id}/statement.csv",
                params=params,
                stream=False,
            )
        if not response.ok:
            raise ValueError("Failed to get statement.  Check private key.")

    def get_cashback_resource_id_date_time_triplets_list(
        self, profile_id: int, params: dict
    ) -> list[tuple[str, str, str]]:
        all_activities = []
        while True:
            activities_response = self.session.get(
                f"{self.url_prefix}/v1/profiles/{profile_id}/activities", params=params
            )
            if not activities_response.ok:
                raise ValueError(f"Error: {activities_response.text}")
            activities = activities_response.json()["activities"]
            all_activities.extend(activities)

            cursor = activities_response.json().get("cursor")
            if not cursor:
                break
            params["nextCursor"] = cursor
        resource_id_list = []
        date_list = []
        time_list = []
        for activity in all_activities:
            if activity["type"] == "BALANCE_CASHBACK":
                resource_id_list.append(activity["resource"]["id"])
                date, time = get_date_and_time(dt_str=activity["createdOn"])
                date_list.append(date)
                time_list.append(time)
        resource_id_date_time_triplets = list(
            zip(resource_id_list, date_list, time_list, strict=True)
        )
        return resource_id_date_time_triplets

    def get_cashback_payouts(
        self, profile_id: int, resource_id: str, params: dict
    ) -> requests.Response:
        response = self.session.get(
            f"{self.url_prefix}/v1/profiles/{profile_id}/cashback-payouts/{resource_id}/details",
            params=params,
        )
        if not response.ok:
            raise ValueError("")
        return response

    def get_cashback_df(
        self, profile_id: int, start_date: date, end_date: date
    ) -> pd.DataFrame:
        cashback_params = {
            "since": f"{start_date.strftime('%Y-%m-%d')}T00:00:00.000Z",
            "until": f"{end_date.strftime('%Y-%m-%d')}T23:59:59.999Z",
            "type": "COMPACT",
        }
        resource_id_date_time_triplets = (
            self.get_cashback_resource_id_date_time_triplets_list(
                profile_id=profile_id, params=cashback_params
            )
        )

        cashback_dict: dict[str, list] = {
            "Resource ID": [],
            "Pre-tax amount": [],
            "Withhholding tax": [],
            "Total cashback": [],
            "Date": [],
            "Time": [],
        }
        for triplet in resource_id_date_time_triplets:
            cashback_dict["Resource ID"].append(triplet[0])
            cashback_dict["Date"].append(triplet[1])
            cashback_dict["Time"].append(triplet[2])
            cashback_payouts = self.get_cashback_payouts(
                profile_id=profile_id, resource_id=triplet[0], params=cashback_params
            ).json()
            cashback_dict["Pre-tax amount"].append(cashback_payouts[5]["description"])
            cashback_dict["Withhholding tax"].append(cashback_payouts[6]["description"])
            cashback_dict["Total cashback"].append(cashback_payouts[8]["description"])
        cashback_df = pd.DataFrame(cashback_dict)
        cashback_df["Date"] = pd.to_datetime(cashback_df["Date"], format="%m-%d-%Y")
        cashback_df["Date"] = cashback_df["Date"].dt.strftime("%d.%m.%Y")
        float_columns = ["Pre-tax amount", "Withhholding tax", "Total cashback"]
        for column in float_columns:
            cashback_df[column] = (
                cashback_df[column].astype(str).str.replace(" EUR", "").astype(float)
            )
        sums = cashback_df[float_columns].sum()
        sum_df = pd.DataFrame(sums).T
        sum_df_total_column_entry = ["TOTAL"]
        sum_df.insert(0, "Resource ID", sum_df_total_column_entry)
        sum_df["Date"] = ""
        sum_df["Time"] = ""
        cashback_df = pd.concat([cashback_df, sum_df]).reset_index(drop=True)
        return cashback_df

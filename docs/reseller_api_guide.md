# 🚀 Reseller API Developer Integration Guide (রিসেলার এপিআই গাইড)

## নিরাপত্তা ও অনুমতির সীমা

- API key দিয়ে নিজের balance, catalog এবং নিজের order দেখা ও order তৈরি করা যায়। সরাসরি balance কমানো/বাড়ানো, deposit approve, refund বা admin API ব্যবহার করা যায় না।
- Order payload কেবল `product_id`, integer `quantity` এবং `custom_id` গ্রহণ করে। Price, customer ID, balance বা অন্য অতিরিক্ত field পাঠালে 422 হবে। দাম ও account server নির্ধারণ করে।
- একই order retry করলে একই `custom_id`/`Idempotency-Key` রাখুন। উভয়টি দিলে মান এক হতে হবে। নতুন key দিলে নতুন order হিসেবে গণ্য হবে এবং আবার charge হতে পারে।
- Key ও reseller status টাকা কাটার transaction-এর মধ্যেও যাচাই হয়। Revoke কার্যকর হওয়ার পরে পুরোনো key দিয়ে নতুন charge হবে না; ইতিমধ্যে committed order নিজে থেকে বাতিল হয় না।
- Wallet charge, stock allocation, order এবং delivery queue একই database transaction-এ লেখা হয়। কোনো ধাপ ব্যর্থ হলে সব rollback হয়। Manual delivery order গ্রহণের সময় charge হয়; delivery পরে হয়।
- API key গোপন রাখুন, শুধু backend থেকে HTTPS-এ ব্যবহার করুন। Key হাতে পেলে কেউ আপনার অনুমতিতেই order করতে পারে; সন্দেহ হলে সঙ্গে সঙ্গে revoke করুন। BDT amount হিসাবের জন্য client-এ decimal arithmetic ব্যবহার করুন।
- Limits: প্রতি account-এ 120 reads এবং 30 writes/minute; shared IP limit 180 API requests/minute। 429 হলে `Retry-After` মেনে retry করুন।

এই গাইডে বিস্তারিত ব্যাখ্যা করা হয়েছে কীভাবে আপনি আমাদের **Reseller API** ব্যবহার করে আপনার নিজস্ব **টেলিগ্রাম বট**, **ওয়েবসাইট**, বা **অটোমেটেড সিস্টেমে** আমাদের প্রোডাক্টগুলো যুক্ত করবেন এবং সরাসরি পাইকারি রিসেলার মূল্যে কেনাকাটা ও তাত্ক্ষণিক ডেলিভারি গ্রহণ করবেন।

---

## 📌 ১. ওভারভিউ ও সুবিধাসমূহ (Overview & Benefits)

* **হোলসেল রিসেলার রেট (`reseller_price`)**: সাধারণ কাস্টমারদের দামের চেয়ে কম মূল্যে আপনি প্রোডাক্ট কিনতে পারবেন।
* **তাত্ক্ষণিক স্বয়ংক্রিয় ডেলিভারি**: এপিআই দিয়ে অর্ডার প্লেস করার সাথে সাথে সেকেন্ডের মধ্যে এপিআই রেসপন্সে প্রোডাক্টের একাউন্ট/লাইসেন্স কি ডেলিভারি হয়ে যাবে।
* **ওয়ালেট ভিত্তিক ব্যালেন্স**: বটে যেভাবে বিকাশ, নগদ বা বাইন্যান্স দিয়ে ব্যালেন্স লোড করেন, সেই ওয়ালেট ব্যালেন্স থেকেই স্বয়ংক্রিয়ভাবে টাকা কাটা হবে।
* **ডাবল চার্জ প্রতিরোধ (Idempotency)**: একই account-এ একই `custom_id`, product ও quantity দিয়ে retry করলে আগের order ফেরত আসে; নতুন charge হয় না।

---

## 🔑 ২. কীভাবে API Key পাবেন?

1. আমাদের টেলিগ্রাম বটে প্রবেশ করুন (যেমন: `@PremiumHaven24Bot`)।
2. যদি আপনার অ্যাকাউন্ট এখনো **Reseller** না হয়ে থাকে, তবে অ্যাডমিনের সাথে যোগাযোগ করে বা নির্ধারিত ডিপোজিট করে রিসেলার এক্সেস নিন।
3. বটে `/reseller` কমান্ড পাঠান অথবা **💼 Apply as a Reseller** বাটনে ক্লিক করুন।
4. **Reseller Partner Dashboard** ওপেন হলে **🔑 Generate API Key** বাটনে চাপুন।
5. আপনার সামনে একটি গোপন এপিআই কি প্রদর্শিত হবে (যেমন: `rk_live_9b4e1837c78096...`)। এটি কপি করে নিরাপদ স্থানে সংরক্ষণ করুন।

---

## 🛡️ ৩. অথেনটিকেশন (Authentication)

প্রতিটি API কল করার সময় নিচের যেকোনো একটি উপায়ে রিকোয়েস্টের **Header**-এ আপনার এপিআই কি পাঠাতে হবে:

**পদ্ধতি ১ (সুপারিশকৃত):**
```http
X-API-Key: rk_live_your_secret_api_key_here
```

**পদ্ধতি ২ (Bearer Token):**
```http
Authorization: Bearer rk_live_your_secret_api_key_here
```

### 🌐 Base URL:
```text
https://YOUR-DOMAIN-NAME/api/v1/reseller
```
*(লোকাল টেস্টিংয়ের জন্য: `http://127.0.0.1:8000/api/v1/reseller`)*

---

## 📦 ৪. এপিআই এন্ডপয়েন্টসমূহ (API Endpoints)

---

### ১. প্রোফাইল ও ব্যালেন্স চেক (Check Balance & Profile)

আপনার অ্যাকাউন্টের বর্তমান ওয়ালেট ব্যালেন্স এবং মোট অর্ডারের সংখ্যা দেখতে এই এন্ডপয়েন্ট কল করুন।

* **Method:** `GET`
* **Path:** `/api/v1/reseller/me`
* **Headers:** `X-API-Key: rk_live_...`

#### রেসপন্স উদাহরণ (200 OK):
```json
{
  "success": true,
  "user": {
    "user_id": 12,
    "tg_user_id": 100200300,
    "username": "reseller_john",
    "name": "John Doe",
    "rank": "Reseller",
    "balance": 2500.0,
    "currency": "BDT",
    "currency_symbol": "৳",
    "total_spent": 8400.0
  },
  "api_key": {
    "prefix": "rk_live_9b4e...3a1f",
    "created_at": "2026-09-20T12:00:00Z",
    "last_used_at": "2026-09-20T15:30:00Z"
  }
}
```

---

### ২. প্রোডাক্ট লিস্ট ও লাইভ স্টক (Fetch Product Catalog)

কোন কোন প্রোডাক্ট বর্তমানে স্টকে আছে এবং আপনার জন্য ডিসকাউন্টেড রিসেলার প্রাইস কত, তা দেখতে এই এন্ডপয়েন্ট কল করুন।

* **Method:** `GET`
* **Path:** `/api/v1/reseller/products`
* **Query Parameters (ঐচ্ছিক):**
  * `category_id` (integer) — নির্দিষ্ট ক্যাটাগরির প্রোডাক্ট ফিল্টার করতে।

#### রেসপন্স উদাহরণ (200 OK):
```json
{
  "success": true,
  "count": 1,
  "currency": "BDT",
  "currency_symbol": "৳",
  "products": [
    {
      "id": 1,
      "title": "NordVPN 1 Month Private Account",
      "category_id": 1,
      "category_name": "VPN Accounts",
      "description": "High-speed VPN account with 6 devices support.",
      "regular_price": 150.0,
      "reseller_price": 120.0,
      "has_discount": true,
      "discount_percent": 20,
      "stock": 14,
      "in_stock": true,
      "delivery_type": "instant",
      "duration": "1 Month",
      "icon": "🛡️"
    }
  ]
}
```

> 💡 **নোট:** `reseller_price` হচ্ছে সেই প্রাইস যা আপনার ওয়ালেট থেকে কাটা হবে। যদি কোনো প্রোডাক্টের বিশেষ রিসেলার রেট সেট না থাকে, তবে স্বয়ংক্রিয়ভাবে নিয়মিত দাম প্রযোজ্য হবে।

---

### ৩. সিঙ্গেল প্রোডাক্ট ডিটেইলস (Get Single Product)

নির্দিষ্ট একটি প্রোডাক্টের লাইভ স্টক ও দাম জানতে:

* **Method:** `GET`
* **Path:** `/api/v1/reseller/products/{product_id}`

---

### ৪. অর্ডার প্লেস করা ও ইনস্ট্যান্ট ডেলিভারি (Place Order & Instant Delivery)

প্রোডাক্ট কিনতে এই এন্ডপয়েন্টে `POST` রিকোয়েস্ট পাঠান। অর্ডার সফল হওয়ার সাথে সাথে **রেসপন্সের ভেতরেই** একাউন্ট ক্রেডেনশিয়াল বা কী চলে আসবে!

* **Method:** `POST`
* **Path:** `/api/v1/reseller/orders`
* **Headers:** 
  * `X-API-Key: rk_live_...`
  * `Content-Type: application/json`

#### রিকোয়েস্ট বডি (JSON Body):
```json
{
  "product_id": 1,
  "quantity": 1,
  "custom_id": "merchant_order_1001"
}
```

| ফিল্ড | টাইপ | বাধ্যতামূলক? | বিবরণ |
| :--- | :--- | :--- | :--- |
| `product_id` | `integer` | **হ্যাঁ** | যে প্রোডাক্টটি কিনতে চান তার আইডি |
| `quantity` | `integer` | না (ডিফল্ট `1`) | কয়টি কিনতে চান (১ থেকে ১০০) |
| `custom_id` | `string` | হ্যাঁ* | ইউনিক অর্ডার আইডি; retry-তে একই আইডি ব্যবহার করুন। *বিকল্প হিসেবে `Idempotency-Key` header দেওয়া যাবে। কোনোটিই না থাকলে 422 ফিরবে। |

#### রেসপন্স উদাহরণ (200 OK — সফল ডেলিভারি):
```json
{
  "success": true,
  "order_id": 492,
  "custom_id": "merchant_order_1001",
  "product_id": 1,
  "product_title": "NordVPN 1 Month Private Account",
  "quantity": 1,
  "unit_price": 120.0,
  "total_price": 120.0,
  "currency": "BDT",
  "currency_symbol": "৳",
  "balance_after": 2380.0,
  "fulfillment": "delivered",
  "credentials": "email: user@gmail.com\npassword: MySecretPassword123",
  "created_at": "2026-09-20T21:45:00Z",
  "message": "Order delivered instantly."
}
```

> ⚡ **ক্রেডেনশিয়াল ব্যবহার:** `credentials` ফিল্ডের টেক্সটটি সরাসরি আপনার কাস্টমারকে পাঠিয়ে দিতে পারবেন!

---

### ৫. অর্ডার স্ট্যাটাস ও ক্রেডেনশিয়াল রি-চেক (Get Order Status)

পূর্বে কৃত কোনো অর্ডারের ক্রেডেনশিয়াল বা স্ট্যাটাস পুনরায় দেখার জন্য:

* **Method:** `GET`
* **Path:** `/api/v1/reseller/orders/{order_id}`

---

### ৬. রিসেলারের পূর্ববর্তী অর্ডার তালিকা (List Orders)

* **Method:** `GET`
* **Path:** `/api/v1/reseller/orders?limit=20&offset=0`

---

## 💻 ৫. কোড ইন্টিগ্রেশন এক্সাম্পল (Code Examples)

---

### ১. Python (টেলিগ্রাম বট বা পাইথন স্ক্রিপ্টের জন্য)

```python
import requests

API_KEY = "rk_live_your_key_here"
BASE_URL = "https://yourdomain.com/api/v1/reseller"
HEADERS = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

def check_balance():
    response = requests.get(f"{BASE_URL}/me", headers=HEADERS)
    data = response.json()
    if response.status_code == 200:
        print(f"Current Balance: {data['user']['balance']} {data['user']['currency_symbol']}")
    else:
        print("Error:", data.get("detail"))

def get_stock(product_id):
    response = requests.get(f"{BASE_URL}/products/{product_id}", headers=HEADERS)
    data = response.json()
    if response.status_code == 200:
        p = data["product"]
        print(f"Product: {p['title']} | Stock: {p['stock']} | Price: {p['reseller_price']}৳")
        return p["in_stock"]
    return False

def buy_product(product_id, client_order_ref):
    payload = {
        "product_id": product_id,
        "quantity": 1,
        "custom_id": str(client_order_ref)
    }
    response = requests.post(f"{BASE_URL}/orders", json=payload, headers=HEADERS)
    result = response.json()
    
    if response.status_code == 200 and result.get("success"):
        print("✅ Order Successful!")
        print("Order ID:", result["order_id"])
        print("Total Charged:", result["total_price"])
        print("Delivered Credentials:\n", result["credentials"])
        return result["credentials"]
    else:
        print("❌ Order Failed:", result.get("detail"))
        return None

if __name__ == "__main__":
    check_balance()
    buy_product(product_id=1, client_order_ref="test_order_001")
```

---

### ২. Node.js / JavaScript (Fetch API)

```javascript
const API_KEY = "rk_live_your_key_here";
const BASE_URL = "https://yourdomain.com/api/v1/reseller";

// ১. ব্যালেন্স চেক
async function getBalance() {
  const res = await fetch(`${BASE_URL}/me`, {
    headers: { "X-API-Key": API_KEY }
  });
  const data = await res.json();
  console.log("Balance:", data.user.balance, data.user.currency_symbol);
}

// ২. অর্ডার দেওয়া
async function orderProduct(productId, customOrderId) {
  const res = await fetch(`${BASE_URL}/orders`, {
    method: "POST",
    headers: {
      "X-API-Key": API_KEY,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      product_id: productId,
      quantity: 1,
      custom_id: customOrderId
    })
  });

  const order = await res.json();
  if (res.ok && order.success) {
    console.log("Order Placed ID:", order.order_id);
    console.log("Credentials:\n", order.credentials);
    return order.credentials;
  } else {
    throw new Error(order.detail || "Order failed");
  }
}
```

---

### ৩. PHP (WordPress / Custom PHP Web)

```php
<?php
$apiKey = "rk_live_your_key_here";
$baseUrl = "https://yourdomain.com/api/v1/reseller";

function placeResellerOrder($productId, $customRef, $apiKey, $baseUrl) {
    $ch = curl_init("$baseUrl/orders");
    $data = json_encode([
        "product_id" => $productId,
        "quantity" => 1,
        "custom_id" => $customRef
    ]);

    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_POST, true);
    curl_setopt($ch, CURLOPT_POSTFIELDS, $data);
    curl_setopt($ch, CURLOPT_HTTPHEADER, [
        "X-API-Key: $apiKey",
        "Content-Type: application/json"
    ]);

    $response = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    $json = json_decode($response, true);
    if ($httpCode === 200 && !empty($json['success'])) {
        return $json['credentials']; // ডেলিভারি একাউন্ট তথ্য
    }
    return false;
}
?>
```

---

### ৪. cURL (টার্মিনাল থেকে টেস্ট করতে)

```bash
# ব্যালেন্স দেখুন:
curl -H "X-API-Key: rk_live_your_key_here" https://yourdomain.com/api/v1/reseller/me

# প্রোডাক্ট লিস্ট দেখুন:
curl -H "X-API-Key: rk_live_your_key_here" https://yourdomain.com/api/v1/reseller/products

# অর্ডার করুন:
curl -X POST https://yourdomain.com/api/v1/reseller/orders \
  -H "X-API-Key: rk_live_your_key_here" \
  -H "Content-Type: application/json" \
  -d '{"product_id": 1, "quantity": 1, "custom_id": "test_curl_01"}'
```

---

## ⚠️ ৬. এরর কোড ও সমাধান (HTTP Error Codes)

| HTTP Code | এরর কারণ | সমাধান |
| :---: | :--- | :--- |
| **`200 OK`** | অর্ডার বা রিকোয়েস্ট সফল | সবকিছু ঠিকঠাক কাজ করেছে। |
| **`401 Unauthorized`** | API Key ভুল বা মিসিং | হেডারে `X-API-Key` সঠিকভাবে পাঠানো হয়েছে কিনা চেক করুন। |
| **`403 Forbidden`** | একাউন্ট Reseller নয় অথবা Banned | অ্যাডমিনের সাথে যোগাযোগ করে নিশ্চিত হোন আপনার একাউন্ট `Reseller` র‍্যাঙ্কে আছে। |
| **`400 Bad Request`** | অপর্যাপ্ত ব্যালেন্স বা স্টক শেষ | রেসপন্সের `detail` মেসেজ দেখুন। যদি ব্যালেন্স না থাকে, তবে টেলিগ্রাম বটে ব্যালেন্স ডিপোজিট করুন। |
| **`404 Not Found`** | প্রোডাক্ট আইডি বা অর্ডার আইডি ভুল | সঠিক `product_id` দিন। |
| **`503 Service Unavailable`** | স্টোরে মেইনটেন্যান্স চলছে | সাময়িক বিরতির পর পুনরায় চেষ্টা করুন। |

---

## 💡 সাহায্য ও সাপোর্ট (Support)
যেকোনো এপিআই ইন্টিগ্রেশন সমস্যা বা সহায়তার জন্য টেলিগ্রাম বটে আমাদের অ্যাডমিন সাপোর্টের সাথে সরাসরি যোগাযোগ করুন।

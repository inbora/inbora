"""Starter knowledge articles. They are added switched off, because the
[brackets] must be replaced with the business's real details first."""

TEMPLATE_KEYS = ["shipping", "returns", "payment", "contact", "hours"]

TEMPLATES: dict[str, dict[str, tuple[str, str]]] = {
    "en": {
        "shipping": ("Shipping", """We ship to [countries / areas].
Delivery time: [X–Y] business days from the order.
Shipping cost: [price]. Free shipping on orders over [amount].
Carrier: [carrier name]. After the order ships, the customer gets a tracking number by [email / SMS]."""),
        "returns": ("Returns and exchanges", """Returns are accepted within [X] days of delivery.
Conditions: the item must be [unused / in its original packaging / with tags].
Not returnable: [items, e.g. personalised products].
To start a return, the customer should [contact us at … / fill in the form at …].
Refunds are made to the original payment method within [X] business days after we receive the item.
Return shipping is paid by [the customer / us].
Exchanges: [how exchanges work]."""),
        "payment": ("Payment", """We accept: [credit cards, PayPal, Apple Pay, bank transfer…].
Instalments: [yes, up to X payments / no].
Payment is [secure / processed by …].
Prices include [VAT / taxes]: [yes / no]."""),
        "contact": ("Contact us", """Email: [address]
Phone / WhatsApp: [number]
Instagram: [@handle]
Address: [address, if customers can visit]
We usually reply within [X hours / one business day]."""),
        "hours": ("Opening hours", """[Sunday–Thursday]: [09:00–18:00]
[Friday]: [09:00–13:00]
[Saturday]: closed
Holidays: [what changes on holidays]."""),
    },
    "he": {
        "shipping": ("משלוחים", """אנחנו שולחים ל[ארצות / אזורים].
זמן אספקה: [X–Y] ימי עסקים מרגע ההזמנה.
עלות משלוח: [מחיר]. משלוח חינם בהזמנה מעל [סכום].
חברת השליחויות: [שם החברה]. לאחר שההזמנה יוצאת, הלקוח מקבל מספר מעקב ב[מייל / SMS]."""),
        "returns": ("החזרות והחלפות", """אפשר להחזיר מוצר עד [X] ימים מקבלת ההזמנה.
תנאים: המוצר צריך להיות [ללא שימוש / באריזה המקורית / עם התוויות].
מוצרים שלא ניתן להחזיר: [למשל מוצרים בהתאמה אישית].
כדי להתחיל החזרה, הלקוח צריך [לפנות אלינו ב… / למלא את הטופס ב…].
ההחזר הכספי מתבצע לאמצעי התשלום המקורי תוך [X] ימי עסקים מקבלת המוצר אצלנו.
דמי המשלוח בהחזרה על חשבון [הלקוח / העסק].
החלפות: [איך מתבצעת החלפה]."""),
        "payment": ("תשלום", """אמצעי תשלום: [כרטיס אשראי, ביט, PayPal, העברה בנקאית…].
תשלומים: [כן, עד X תשלומים / לא].
התשלום [מאובטח / מתבצע דרך …].
המחירים כוללים מע״מ: [כן / לא]."""),
        "contact": ("יצירת קשר", """מייל: [כתובת]
טלפון / וואטסאפ: [מספר]
אינסטגרם: [@שם]
כתובת: [כתובת, אם אפשר להגיע]
אנחנו עונים בדרך כלל תוך [X שעות / יום עסקים]."""),
        "hours": ("שעות פעילות", """[ראשון–חמישי]: [09:00–18:00]
[שישי]: [09:00–13:00]
שבת: סגור
חגים: [מה משתנה בחגים]."""),
    },
    "ar": {
        "shipping": ("الشحن", """نشحن إلى [الدول / المناطق].
مدة التوصيل: [X–Y] أيام عمل من تاريخ الطلب.
تكلفة الشحن: [السعر]. الشحن مجاني للطلبات فوق [المبلغ].
شركة الشحن: [اسم الشركة]. بعد شحن الطلب يحصل العميل على رقم تتبع عبر [البريد الإلكتروني / رسالة SMS]."""),
        "returns": ("الإرجاع والاستبدال", """يمكن إرجاع المنتج خلال [X] يومًا من الاستلام.
الشروط: يجب أن يكون المنتج [غير مستخدم / في عبوته الأصلية / مع الملصقات].
منتجات لا يمكن إرجاعها: [مثل المنتجات المخصصة].
لبدء الإرجاع، على العميل [التواصل معنا عبر … / تعبئة النموذج في …].
يُعاد المبلغ إلى وسيلة الدفع الأصلية خلال [X] أيام عمل بعد استلامنا للمنتج.
تكلفة شحن الإرجاع على [العميل / المتجر].
الاستبدال: [كيف يتم الاستبدال]."""),
        "payment": ("الدفع", """وسائل الدفع: [بطاقة ائتمان، PayPal، Apple Pay، تحويل بنكي…].
التقسيط: [نعم، حتى X دفعات / لا].
الدفع [آمن / يتم عبر …].
الأسعار تشمل الضريبة: [نعم / لا]."""),
        "contact": ("تواصل معنا", """البريد الإلكتروني: [العنوان]
الهاتف / واتساب: [الرقم]
إنستغرام: [@الاسم]
العنوان: [العنوان، إن كان بإمكان العملاء الزيارة]
نرد عادةً خلال [X ساعات / يوم عمل]."""),
        "hours": ("ساعات العمل", """[الأحد–الخميس]: [09:00–18:00]
[الجمعة]: [09:00–13:00]
السبت: مغلق
العطل: [ما الذي يتغير في العطل]."""),
    },
}

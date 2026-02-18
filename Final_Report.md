Stroke Prediction - Data Analysis Report
1. Executive Summary
تم تحليل ومعالجة بيانات تحتوي على 93,400 سجل للتنبؤ بحالات السكتة الدماغية. الهدف هو تجهيز داتا نظيفة تماماً لبناء موديل ذكاء اصطناعي دقيق.

2. Data Preprocessing (ما تم فعله في الداتا)
Handling Missing Values: تم التعامل مع القيم المفقودة في عمود الـ bmi باستخدام الـ Median، وعمود الـ smoking_status بتصنيفه كـ Unknown.

Feature Scaling: تم توحيد مقاييس الأرقام (Age, Glucose, BMI) باستخدام StandardScaler لضمان عدم طغيان رقم كبير على رقم صغير.

Encoding: تم تحويل البيانات النصية لأرقام (Male/Female -> 0/1) واستخدام One-Hot Encoding لأنواع العمل وحالة التدخين.

Data Cleaning: تم حذف عمود الـ id لأنه لا يمثل قيمة تحليلية ويؤدي لتشتيت الموديل.

3. Key Exploratory Insights (أهم الاكتشافات)
Target Imbalance: الداتا غير متوازنة، حيث أن 3.4% فقط من الحالات مصابة بالجلطة. (توصية: استخدام SMOTE عند التدريب).

Age Factor: السن هو أقوى عامل مرتبط بالإصابة، حيث تزداد الكثافة بشكل ملحوظ بعد سن الـ 60.

Glucose Correlation: هناك علاقة واضحة بين ارتفاع مستوى السكر في الدم وزيادة احتمالية الإصابة بالجلطة.

Smoking Insight: وجدنا أن المدخنين السابقين (Formerly Smoked) معرضون للخطر بنسبة تقارب المدخنين الحاليين.

4. Deliverables (الملفات المسلمة)
stroke_data_for_ml.csv: البيانات النهائية الجاهزة للتدريب.

feature_scaler.pkl: ملف الميزان الخاص بالبيانات (Scaler) لاستخدامه في مرحلة التوقع (Inference).
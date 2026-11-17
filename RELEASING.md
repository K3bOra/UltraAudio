## Package control validation (1.0.29)

Control fields must be in exactly one paragraph. Insert X-UltraAudio-Family before the terminal newline; never add a blank separator before it. The 1.0.28 release contained that separator and dpkg rejected it as multiple package entries. Release 1.0.29 corrects the metadata without changing UI, audio or timeshift.

`prepare_release.py` now checks paragraph/field uniqueness and invokes `dpkg-deb --field` on all four packages. `tests/test_control_metadata.py` reproduces the malformed metadata, tests the native parser, and runs `dpkg --no-act --unpack` with isolated databases for both DEB variants. These checks are required before publication.

## Four isolated update variants (1.0.28 onwards)

Publish all four entries in `scripts/release_variants.py` together. Preserve each supplied source family. One/Two IPK and DEB must never be built from the ordinary receiver source tree. All versions advance together; DEB appends `-dreamos`.

The updater is pinned to both image package manager and receiver family. The unified installer detects One/Two model names independently of the package manager. Missing special manifests fail without falling back to ordinary packages. Control metadata includes `X-UltraAudio-Family` and is checked before installation.

Run `scripts/render_installer.py`, `scripts/prepare_release.py`, `scripts/unpack_sources.py` (fresh checkout), `tests/test_updates.py`, `tests/test_e2pc_updates.py`, and `tests/test_release_families.py`. The release workflow verifies all four public downloads before refreshing bootstrap manifests.

The 1.0.28 input packages were user-supplied. Only version metadata and updater routing were changed; audio, timeshift, UI and assets were preserved. See `packages/release28-verification.json`.

<div dir="rtl">

# نشر تحديثات Ultra Audio

المصدر الرسمي هو `K3bOra/UltraAudio`. تم تجهيز إجراء نشر **يدوي فقط**؛ حفظ الملفات أو رفعها للمستودع لا ينشر إصدارًا تلقائيًا.

عند تجهيز تحديث جديد، توضع الحزمتان IPK وDreamOS DEB في `packages/` وتُكتب ملاحظات كل مسار في `release-notes.json`. يرتفع الرقم الأساسي في الحزمتين معًا: `1.0.13` و`1.0.13-dreamos`، ثم 14 ثم 15 ثم 16. يرفض تجهيز الإصدار اختلاف الرقمين، مع إبقاء اسم المنتج Ultra Audio Final V1. يُشغَّل إجراء **Publish verified UltraAudio release** يدويًا عند طلب النشر فقط.

سكربت التجهيز يفحص اسم الحزمة ورقمها ومحتوياتها، ويحسب الحجم وبصمة SHA-256 من الملف الفعلي. ثم يجهز إجراء النشر مسودة، ويتحقق من الملفات المرفوعة قبل إتاحة الإصدار. لا يُستبدل إصدار سبق نشره.

التحديث الأونلاين يقرأ `update-ipk.json` أو `update-dreamos.json` حسب البيئة، ويعرض الملاحظات ويطلب موافقة المستخدم قبل التثبيت. يبقى `update.json` مطابقًا لمسار IPK لدعم النسخ القديمة. يجب أن يحتوي كل إصدار الحزمتين والمثبت وملفات التحديث الثلاثة وSHA256SUMS. لن يُنشَر ملف تحديث تجريبي يشير إلى حزمة غير موجودة.

استخرج المصدر الكامل للحزمتين بأمر `python3 -B scripts/unpack_sources.py` إلى `ipk-source/` و`deb-source/`؛ لا تُخلط تعديلات تشغيل الدريم مع مصدر IPK. للتجهيز المحلي: `python3 -B scripts/render_installer.py` ثم `python3 -B scripts/build_packages.py` ثم `python3 -B tests/run_local.py`. اختبارات الصوت الاختيارية تحتاج ffmpeg: `UA_TEST_MAX_DELAY=1 python3 -B tests/run_local.py --audio`.

الانتقال من ترقيم DreamOS القديم 23/24 إلى 13 يتم مرة واحدة من المثبت الموحّد. علامة VERSION_SCHEME في ملف إصدار DreamOS تميز السلسلة الجديدة، وتمنع اعتبار الإصدار 23 المستقبلي إصدارًا قديمًا. التحديث الأونلاين يحتفظ بترتيب تصاعدي عادي. لم تُختبر تعريفات الصوت أو Python 2 على جهاز Dreambox فعلي في بيئة البناء؛ تُضاف نتائج اختبارات الأجهزة عند توفرها.

</div>

المثبت المنشور في main يُحدَّث تلقائيًا بعد رفع الإصدار والتحقق من تحميل الحزمتين؛ workflow يولده أولًا محليًا من القالب. بذلك يظل أمر التثبيت الحالي متاحًا حتى تجهيز ملفات القناتين. لا ترفع install.sh يدويًا قبل نجاح نشر الحزمتين.

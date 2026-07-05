/* Smart Health Navigator – Contact Form */
document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('contactForm');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const btn        = form.querySelector('button[type="submit"]');
    const successMsg = document.getElementById('successMsg');
    const errorMsg   = document.getElementById('errorMsg');

    // Reset state
    successMsg.style.display = 'none';
    errorMsg.style.display   = 'none';
    btn.disabled    = true;
    btn.textContent = '⏳ Sending…';

    const name    = (document.getElementById('name')?.value    || '').trim();
    const email   = (document.getElementById('email')?.value   || '').trim();
    const subject = (document.getElementById('subject')?.value || '').trim();
    const msgBody = (document.getElementById('message')?.value || '').trim();

    // Basic client-side validation
    if (!name || !email || !msgBody) {
      errorMsg.textContent = '❌ Please fill in all required fields.';
      errorMsg.style.display = 'block';
      btn.disabled    = false;
      btn.textContent = '✉️ Send Message';
      return;
    }

    // Include subject in message body so it shows in admin
    const fullMessage = subject ? `[Subject: ${subject}]\n\n${msgBody}` : msgBody;

    try {
      const res = await fetch('/api/contact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email, message: fullMessage })
      });

      // Check if response is even OK
      if (!res.ok) {
        const errText = await res.text();
        throw new Error(`Server error ${res.status}: ${errText}`);
      }

      const data = await res.json();

      if (data.success) {
        successMsg.textContent = '✅ Message sent successfully! We will get back to you within 24–48 hours.';
        successMsg.style.display = 'block';
        successMsg.scrollIntoView({ behavior: 'smooth', block: 'center' });
        form.reset();
      } else {
        throw new Error(data.error || 'Unknown server error');
      }
    } catch (err) {
      errorMsg.textContent = '❌ Failed to send: ' + err.message;
      errorMsg.style.display = 'block';
      errorMsg.scrollIntoView({ behavior: 'smooth', block: 'center' });
    } finally {
      btn.disabled    = false;
      btn.textContent = '✉️ Send Message';
    }
  });
});

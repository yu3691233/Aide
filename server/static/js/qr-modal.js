let qrCodeInstance = null;

function showQRModal(ip) {

  if (!ip || ip === '—') {

    showToast('暂无有效局域网IP', 'error');

    return;

  }

  const url = `http://${ip}:5000`;

  document.getElementById('qr-url-text').textContent = url;

  document.getElementById('qr-modal').style.display = 'flex';

  document.getElementById('qrcode-canvas').innerHTML = '';

  qrCodeInstance = new QRCode(document.getElementById('qrcode-canvas'), {

    text: url,

    width: 200,

    height: 200,

    colorDark : "#000000",

    colorLight : "#ffffff",

    correctLevel : QRCode.CorrectLevel.H

  });

}

function closeQRModal() {

  document.getElementById('qr-modal').style.display = 'none';

}

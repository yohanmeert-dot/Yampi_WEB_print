async function syncOrders() {

    const button = event.target;

    button.innerText = "Sincronizando...";

    try {

        const response = await fetch("/api/yampi/sync");

        const data = await response.json();

        if (data.ok) {

            alert(
                `Pedidos sincronizados!\n\nRecebidos: ${data.total_received}\nNovos salvos: ${data.saved}`
            );

            location.reload();

        } else {

            alert("Erro ao sincronizar.");

            console.log(data);

        }

    } catch (err) {

        console.error(err);

        alert("Erro inesperado.");

    }

    button.innerText = "Sincronizar Pedidos";
}


function printOrder(orderId) {

    const iframe = document.createElement("iframe");

    iframe.style.position = "fixed";
    iframe.style.right = "0";
    iframe.style.bottom = "0";
    iframe.style.width = "0";
    iframe.style.height = "0";
    iframe.style.border = "0";
    iframe.style.opacity = "0";

    iframe.src = `/print/${orderId}?auto=1`;

    document.body.appendChild(iframe);

    iframe.onload = function () {
        setTimeout(() => {
            iframe.contentWindow.focus();
            iframe.contentWindow.print();
        }, 500);
    };

    setTimeout(() => {
        iframe.remove();
    }, 15000);
}

async function markPreparing(orderId) {

    await fetch(`/api/orders/${orderId}/status`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            order_status: "em preparo"
        })
    });

    location.reload();
}


async function markFinished(orderId) {

    await fetch(`/api/orders/${orderId}/status`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            order_status: "finalizado"
        })
    });

    location.reload();
}


async function saveOrderInfo(orderId) {

    const payment = document.getElementById(`payment-${orderId}`).value;

    const notes = document.getElementById(`notes-${orderId}`).value;

    await fetch(`/api/orders/${orderId}/status`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            local_payment_method: payment,
            notes: notes
        })
    });

    alert("Alterações salvas!");

    location.reload();
}


// ===============================
// SOM DE SINO
// ===============================

function playBellSound() {

    const audioCtx = new (
        window.AudioContext ||
        window.webkitAudioContext
    )();

    function bell(freq, start, duration) {

        const osc = audioCtx.createOscillator();

        const gain = audioCtx.createGain();

        osc.type = "sine";

        osc.frequency.value = freq;

        gain.gain.setValueAtTime(0.0001, start);

        gain.gain.exponentialRampToValueAtTime(
            0.5,
            start + 0.01
        );

        gain.gain.exponentialRampToValueAtTime(
            0.0001,
            start + duration
        );

        osc.connect(gain);

        gain.connect(audioCtx.destination);

        osc.start(start);

        osc.stop(start + duration);
    }

    const now = audioCtx.currentTime;

    // DING
    bell(1200, now, 0.5);

    // DING 2
    bell(900, now + 0.22, 0.6);
}


// ===============================
// AUTO ATUALIZAÇÃO
// ===============================

let syncingNow = false;

async function autoSyncOrders() {

    if (syncingNow) {
        return;
    }

    syncingNow = true;

    try {

        const response = await fetch("/api/yampi/sync");

        const data = await response.json();

        if (data.ok) {

            if (data.saved > 0) {

                console.log(
                    "NOVOS PEDIDOS:",
                    data.saved
                );

                playBellSound();

                setTimeout(() => {
                    location.reload();
                }, 1200);
            }
        }

    } catch (err) {

        console.error(
            "Erro auto sync:",
            err
        );

    }

    syncingNow = false;
}


// roda a cada 5 segundos
setInterval(autoSyncOrders, 5000);
function printOrderHidden(orderId) {

    const iframe = document.createElement("iframe");

    iframe.style.position = "fixed";
    iframe.style.right = "0";
    iframe.style.bottom = "0";
    iframe.style.width = "0";
    iframe.style.height = "0";
    iframe.style.border = "0";
    iframe.style.opacity = "0";

    iframe.src = `/print/${orderId}?auto=1`;

    document.body.appendChild(iframe);

    setTimeout(() => {
        iframe.remove();
    }, 15000);
}
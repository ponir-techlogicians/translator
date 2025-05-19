document.addEventListener('DOMContentLoaded', function() {
    const overlay    = document.getElementById('modal-overlay');
    const btn        = document.getElementById('translateBtn');
    const mBig       = document.getElementById('modal-bigfile');
    const mMany      = document.getElementById('modal-manylang');
    const mPay       = document.getElementById('modal-payment');
    const closers    = document.querySelectorAll('.modal-close, .modal-x, .modal-confirm');

    function openModal(modal) {
        overlay.classList.add('active');
        modal.classList.add('active');
    }
    function closeModal() {
        overlay.classList.remove('active');
        [mBig, mMany, mPay].forEach(m => m.classList.remove('active'));
    }

    window.showBigFileModal      = () => openModal(mBig);
    window.showTooManyLangModal  = () => openModal(mMany);
    window.showPaymentModal      = () => openModal(mPay);

    // Translate 버튼 클릭 → 조건에 따라 모달 오픈
    // btn.addEventListener('click', function() {
    //     showTooManyLangModal();
    // });

    // 오버레이 또는 닫기 버튼 클릭 시 모두 닫기
    overlay.addEventListener('click', closeModal);
    closers.forEach(btn => btn.addEventListener('click', closeModal));


    let dropArea = document.getElementById('drop-area');
    let fileInput = document.getElementById('fileInput');
    let fileNameDisplay = document.getElementById('file-name');
    let form = document.getElementById('translateForm');
    let loadingSpinner = document.getElementById('loadingSpinner');
    let priceModal = document.getElementById('price-modal');

    document.querySelector('.close-modal').addEventListener('click', function () {
        priceModal.style.display = 'none';
        loadingSpinner.style.display = 'none';
    });

    let stripe = Stripe('{{ stripe_key }}');
    let elements = stripe.elements();

    dropArea.addEventListener('dragover', (event) => {
        event.preventDefault();
        dropArea.classList.add('highlight');
    });

    dropArea.addEventListener('dragleave', () => {
        dropArea.classList.remove('highlight');
    });

    dropArea.addEventListener('drop', (event) => {
        event.preventDefault();
        dropArea.classList.remove('highlight');

        let files = event.dataTransfer.files;
        if (files.length > 0) {
            fileInput.files = files;
            fileNameDisplay.textContent = files[0].name;
        }
    });

    dropArea.addEventListener('click', () => {
        fileInput.click();
    });

    fileInput.addEventListener('change', (event) => {
        if (event.target.files.length > 0) {
            fileNameDisplay.textContent = event.target.files[0].name;
        }
    });

    form.addEventListener('submit', function (e) {
                e.preventDefault();
                loadingSpinner.style.display = 'inline-block';
                const formData = new FormData(form);
                //$("#modal-payment").show();
                $.ajax({
                    url: "/price-estimate/",
                    type: "POST",
                    data: formData,
                    contentType: false,
                    processData: false,
                    success: function (response) {
                        $("#modal-payment").show();
                        estimatedPrice = response.price;
                        $("#usage_id").val(response.usage_id);
                        var html = `<p> $ ${estimatedPrice} for translation </p>`;
                        $("#price-message").html(html);
                        $("#stripe-payment").show();
                    },
                    error: function (xhr) {
                        if (xhr.responseJSON) {
                            $('.error-msg').html(xhr.responseJSON.message);
                            $('.error-reason').html(xhr.responseJSON.reason);
                            showBigFileModal();
                            //$("#price-message").html(`<p style="color: red; font-weight: bold;">${xhr.responseJSON.message}</p>`);
                        } else {
                            $("#modal-payment").show();
                           $("#price-message").html('<p style="color: red; font-weight: bold;">Error estimating price.</p>');
                        }
                        $("#stripe-payment").hide();
                        loadingSpinner.style.display = 'none';
                    }
                });
    });
});
setTimeout(() => {
    const flashMessages = document.querySelectorAll(".flash-message");
    flashMessages.forEach(msg => {
        msg.style.transition = "0.4s ease";
        msg.style.opacity = "0";
        msg.style.transform = "translateY(-6px)";
        setTimeout(() => {
            msg.remove();
        }, 400);
    });
}, 3000);  
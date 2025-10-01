// Landscape orientation warning for mobile devices
(function() {
    'use strict';

    function checkOrientation() {
        // Check if device is mobile (max-width 768px) and in landscape mode
        const isMobile = window.matchMedia('(max-width: 768px)').matches;
        const isLandscape = window.matchMedia('(orientation: landscape)').matches;
        const modal = document.getElementById('kko-landscape-warning');

        if (!modal) return;

        if (isMobile && isLandscape) {
            // Show modal using UIKit
            UIkit.modal(modal).show();
        } else {
            // Hide modal using UIKit
            UIkit.modal(modal).hide();
        }
    }

    // Check on load
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', checkOrientation);
    } else {
        checkOrientation();
    }

    // Check on orientation change
    window.addEventListener('orientationchange', function() {
        // Small delay to ensure orientation has fully changed
        setTimeout(checkOrientation, 100);
    });

    // Also listen to resize events as backup
    window.addEventListener('resize', checkOrientation);
})();

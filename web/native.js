import { Capacitor, registerPlugin } from '@capacitor/core';
import { PushNotifications } from '@capacitor/push-notifications';
window.NottleNative = { native: Capacitor.isNativePlatform(), push: PushNotifications, sms: registerPlugin('CustomerSms') };
window.dispatchEvent(new Event('nottle-native-ready'));

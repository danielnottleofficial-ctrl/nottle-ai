package com.nottleai.app;

import android.content.Intent;
import android.net.Uri;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

@CapacitorPlugin(name = "CustomerSms")
public class CustomerSmsPlugin extends Plugin {
    @PluginMethod
    public void compose(PluginCall call) {
        String phone = call.getString("phone", "");
        if (!phone.matches("\\+?[0-9]{6,15}")) {
            call.reject("A valid customer phone number is required.");
            return;
        }
        Intent intent = new Intent(Intent.ACTION_SENDTO, Uri.fromParts("smsto", phone, null));
        intent.putExtra("sms_body", call.getString("body", ""));
        try {
            getActivity().startActivity(intent);
            call.resolve();
        } catch (android.content.ActivityNotFoundException exception) {
            call.reject("No SMS app is installed on this phone.");
        }
    }
}

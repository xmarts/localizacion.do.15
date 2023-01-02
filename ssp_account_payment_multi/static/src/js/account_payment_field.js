odoo.define('ssp_account_payment_multi.payment_field', function (require) {
"use strict";

var AbstractField = require('web.AbstractField');
var core = require('web.core');
var field_registry = require('web.field_registry');
var field_utils = require('web.field_utils');

var Widget = require('account.payment');
var ShowPaymentLineWidget = Widget.ShowPaymentLineWidget
var QWeb = core.qweb;
var _t = core._t;

ShowPaymentLineWidget.include({
    events: _.extend({}, ShowPaymentLineWidget.prototype.events, {
        'click .outstanding_multi_credit_assign': '_onOutstandingMultiCreditAssign',
    }),
    _onOutstandingMultiCreditAssign: function (event) {
        event.stopPropagation();
        event.preventDefault();
        var info = JSON.parse(this.value);
        var invoiceMoveId = info.move_id;
        var index = $(event.target).data('index');
        var amount = info.content[index]['amount'];
        //Move line payable or receivable account.move.line
        var move_line = info.content[index]['id'];
        //Asiento Contalbe del pago account.move
        var move_id_payment = info.content[index]['move_id'];

        var self = this;
        this.do_action({
            name: _t('Register Partial Payment'),
            type: 'ir.actions.act_window',
            res_model: 'account.payment.partial.register',
            view_mode: 'form',
            views: [[false, 'form']],
            target: 'new',
            context: {
                'active_model': 'account.move',
                'active_ids': [invoiceMoveId],
                'default_account_payable_or_receivable_id': move_line,
                'default_pay_entries_move_id': move_id_payment,
                'amount_remaining': amount
            },

        });
    },
})
return ShowPaymentLineWidget;
})

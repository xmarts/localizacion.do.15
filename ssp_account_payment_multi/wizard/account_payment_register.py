# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.tools.misc import formatLang
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero


class AccountPaymentPartialRegister(models.TransientModel):
    _name = 'account.payment.partial.register'
    _description = 'Register Partial Payment'

    payment_id = fields.Many2one('account.payment')
    # Movimineot de facturacion line?ids

    # == Business fields ==
    payment_line_ids = fields.One2many(related='payment_id.line_ids')

    active_move_id = fields.Many2one('account.move', string="Document Active")
    active_move_type = fields.Selection(related='active_move_id.move_type')
    active_move_partner = fields.Many2one(related='active_move_id.partner_id')
    active_move_date = fields.Date(related='active_move_id.invoice_date')
    active_move_date_due = fields.Date(related='active_move_id.invoice_date_due')
    active_move_currency = fields.Many2one(related='active_move_id.currency_id')
    active_move_total = fields.Monetary(related='active_move_id.amount_total', currency_field='active_move_currency')
    active_move_residual = fields.Monetary(related='active_move_id.amount_residual', currency_field='active_move_currency')

    name =  fields.Char(related='payment_id.name')
    company_id = fields.Many2one(related='payment_id.company_id')
    company_currency_id = fields.Many2one(related='company_id.currency_id', string="Company Currency")
    journal_id = fields.Many2one(related='payment_id.journal_id')
    date_payment = fields.Date(related='payment_id.date')
    ref = fields.Char(related='payment_id.ref')

    is_reconciled = fields.Boolean(related='payment_id.is_reconciled')
    is_matched = fields.Boolean(related='payment_id.is_matched')
    # == Payment methods fields ==

    # == Synchronized fields with the account.move.lines ==
    payment_type = fields.Selection(related='payment_id.payment_type')
    partner_type = fields.Selection(related='payment_id.partner_type')
    payment_reference = fields.Char(related='payment_id.payment_reference')
    payment_currency_id = fields.Many2one(related='payment_id.currency_id', string="Currenvy Payment")

    partner_id = fields.Many2one(related='payment_id.partner_id')
    destination_account_id = fields.Many2one(related='payment_id.destination_account_id')

    # == Display purpose fields ==
    entries_pay_move_id = fields.Many2one('account.move')
    account_payable_or_receivable = fields.Many2one('account.move.line')
    matched_debit_ids = fields.One2many(related='account_payable_or_receivable.matched_debit_ids')
    matched_credit_ids = fields.One2many(related='account_payable_or_receivable.matched_credit_ids')

    amount = fields.Monetary(related="payment_id.amount", string="Amount Payment", currency_field='payment_currency_id', readonly="1")
    #amount remaining
    amount_residual = fields.Monetary(string="Aavailable Amount", compute="_compute_amount_residual", currency_field='payment_currency_id', readonly="1")
    amount_partial = fields.Monetary(string='Partial Amount', currency_field='payment_currency_id')


    @api.depends('amount', 'account_payable_or_receivable', 'matched_debit_ids', 'matched_credit_ids')
    def _compute_amount_residual(self):
        self.ensure_one()
        amount_residual = abs(self.account_payable_or_receivable.amount_residual_currency)
        sum_partial_amount = 0.0

        if self.active_move_id.is_sale_document(include_receipts=True):

            sum_partial_amount = sum(self.matched_credit_ids.mapped('amount'))

            if self.payment_id.currency_id.id != self.company_currency_id.id:
                sum_partial_amount = self.company_currency_id._convert(
                    sum_partial_amount,
                    self.payment_id.currency_id,
                    self.company_id,
                    self.payment_id.date
                )
        else:
            sum_partial_amount = sum(self.matched_debit_ids.mapped('amount'))

            if self.payment_id.currency_id.id != self.company_currency_id.id:
                sum_partial_amount = self.company_currency_id._convert(
                    sum_partial_amount,
                    self.payment_id.currency_id,
                    self.company_id,
                    self.payment_id.date
                )

        self.amount_residual = abs(amount_residual) - abs(sum_partial_amount)

    #---------------------------------------------------------------------
    # LOW-LEVEL METHODS
    # -------------------------------------------------------------------------
    @api.model
    def default_get(self, fields):
        result = super(AccountPaymentPartialRegister, self).default_get(fields)

        # Linea move line
        context_move_line_id = self.env.context.get('default_account_payable_or_receivable_id')
        context_active_move_id = self._context.get('active_ids', [])
        context_entries_pay_move_id = self._context.get('default_pay_entries_move_id')

        # Asiento contable entrada Payment
        entries_pay_move_id = self.env['account.move'].browse(context_entries_pay_move_id)
        # Apunte Contable de cuentas por cobrar/pagar del Pago
        account_payable_or_receivable = self.env['account.move.line'].browse(context_move_line_id)
        # Asiento contable de factura
        active_move_id = self.env['account.move'].browse(context_active_move_id)

        result.update({
            'account_payable_or_receivable': account_payable_or_receivable.id, #apunte contable de cuenta por paga o cobrar
            'entries_pay_move_id': entries_pay_move_id.id, #Asiento contable del pago, move_id, partida doble
            'payment_id': entries_pay_move_id.payment_id.id,  # Pago account payment
            'active_move_id': active_move_id.id, #Account move Factura
        })
        return result

    def create_partial_payment(self, active_move_id, payment_move_id, amount_partial):

        domain = [('account_internal_type', 'in', ('receivable', 'payable'))]

        # Cuenta por cobrar o pagar de la factura
        account_payable_or_receivable = active_move_id.line_ids.filtered_domain(domain)
        to_reconcile = [account_payable_or_receivable]
        amount_partial = amount_partial

        payments = payment_move_id

        # to_reconcile_payments = [payments.line_ids.filtered_domain(domain)]
        signo = None
        if self.payment_type == 'inbound' and self.partner_type == 'customer':
            signo = -1
        if self.payment_type == 'outbound' and self.partner_type == 'customer':
            signo = 1
        if self.payment_type == 'inbound' and self.partner_type == 'supplier':
            signo = 1
        if self.payment_type == 'outbound' and self.partner_type == 'supplier':
            signo = -1

        for payment, lines in zip(payments, to_reconcile):

            payment_lines = payment.line_ids.filtered_domain(domain)
            payment_lines = payment_lines.with_context(amount=amount_partial, date=self.date_payment, signo=signo,
                                                       multi_partial=True)
            for account in payment_lines.account_id:
                move_lines = (payment_lines + lines) \
                    .filtered_domain([('account_id', '=', account.id)])
                move_lines.reconcile()

        return True

    def _create_payments_partial(self):
        self.ensure_one()
        for record in self.payment_id:
            if float_is_zero(self.amount_partial, precision_rounding=self.active_move_currency.rounding):
                continue
            # get el move id,  factura a la cual se le abonara el pago
            payment_move_id = record.move_id
            # get el amount partial, captura el monto partial abonado
            amount_partial = 0.0
            if record.currency_id.id != record.company_currency_id.id:
                amount_partial = payment_move_id.currency_id._convert(
                    self.amount_partial,
                    payment_move_id.company_currency_id,
                    payment_move_id.company_id,
                    payment_move_id.date
                )
            else:
                amount_partial = self.amount_partial


            self.create_partial_payment(self.active_move_id, payment_move_id, amount_partial)
        return True

    def action_create_payments(self):

        if self.amount_partial > self.amount or self.amount_partial > self.amount_residual:
            raise ValidationError(_("The partial amount cannot be greater than the available amount"))

        if self.amount_partial <= 0 :
            raise ValidationError(_("The partial amount cannot be zero"))

        payments = self._create_payments_partial()
        action = {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.active_move_id.id,
        }
        return action


class AccountPaymentPartial(models.TransientModel):
    _name = 'account.payment.partial'
    _description = 'Document Account Payment Partial'

    wizard_id = fields.Many2one('account.payment.multi.partial.register')
    payment_id = fields.Many2one(related='wizard_id.payment_id')
    payment_type = fields.Selection(related='payment_id.payment_type')
    partner_type = fields.Selection(related='payment_id.partner_type')
    partner_id = fields.Many2one(related='payment_id.partner_id')
    move_id = fields.Many2one('account.move', string='Document')

    #domain_move_id = fields.Many2one(compute="_compute_domain_move_id", readonly=True, store=False)
    currency_id = fields.Many2one(related='move_id.currency_id', string="Currency")
    payment_currency_id = fields.Many2one(related='payment_id.currency_id', string="Moneda Pago")
    company_id = fields.Many2one(related='payment_id.company_id', string="Company")
    company_currency_id = fields.Many2one(related='company_id.currency_id', string="COmpany Currency")

    origin = fields.Char(related='move_id.invoice_origin')
    date_invoice = fields.Date(related='move_id.invoice_date')
    date_due = fields.Date(related='move_id.invoice_date_due')
    payment_state = fields.Selection(related='payment_id.state', store=True)
    partial_amount = fields.Monetary(string='Partial Amount', readonly=False)
    amount_total = fields.Monetary(related="move_id.amount_total", string="Total Currency")
    amount_total_signed = fields.Monetary(related="move_id.amount_total_signed", string="Total Company Currency")

    amount_untaxed_signed = fields.Monetary(related="move_id.amount_untaxed_signed", string="Untaxed Company Currency")
    amount_tax_signed = fields.Monetary(related="move_id.amount_tax_signed", string="Tax Company Currency")
    #amount_residual
    residual = fields.Monetary(related="move_id.amount_residual", string="Residual Currency")
    amount_residual_signed = fields.Monetary(related="move_id.amount_residual_signed", string="Residual Company Currency")

    domain_payment_move_ids = fields.Many2many(
        comodel_name="account.move",
        compute="_compute_domain_payment_move_ids",
        string="Domain Move Id",
    )

    @api.depends('partner_id')
    def _compute_domain_payment_move_ids(self):
        account_move = self.env['account.move']
        for record in self:
            if record.payment_type == 'inbound' and record.partner_type == 'customer':
                domain = account_move.search(
                    [('partner_id', '=', record.partner_id.id), ('payment_state', 'in', ('not_paid', 'partial')),
                     ('state', '=', 'posted'), ('move_type', 'in', ('out_invoice', 'out_receipt'))])
            elif record.payment_type == 'outbound' and record.partner_type == 'customer':
                domain = account_move.search(
                    [('partner_id', '=', record.partner_id.id), ('payment_state', 'in', ('not_paid', 'partial')),
                     ('state', '=', 'posted'), ('move_type', '=', 'out_refund')])
            elif record.payment_type == 'outbound' and record.partner_type == 'supplier':
                domain = account_move.search(
                    [('partner_id', '=', record.partner_id.id), ('payment_state', 'in', ('not_paid', 'partial')),
                     ('state', '=', 'posted'), ('move_type', 'in', ('in_invoice', 'in_receipt'))])
            else:
                domain = account_move.search(
                    [('partner_id', '=', record.partner_id.id), ('payment_state', 'in', ('not_paid', 'partial')),
                     ('state', '=', 'posted'), ('move_type', '=', 'in_refund')])
            record.domain_payment_move_ids = domain.ids


class AccountPaymentMultiPartialRegister(models.TransientModel):
    _name = 'account.payment.multi.partial.register'
    _description = 'Register Multi Partial Payment'

    @api.depends('payment_id', 'amount')
    def compute_account_payable_or_receivable(self):
        domain = [('account_internal_type', 'in', ('receivable', 'payable'))]
        for payment in self:
            entries_lines = payment.payment_id.move_id.line_ids.filtered_domain(domain)
            payment.account_payable_or_receivable = entries_lines.id

    payment_id = fields.Many2one('account.payment')
    # Movimineot de facturacion line?ids
    amount = fields.Monetary(related='payment_id.amount')
    payment_type = fields.Selection(related='payment_id.payment_type')
    partner_type = fields.Selection(related='payment_id.partner_type')
    currency_id = fields.Many2one(related='payment_id.currency_id')

    date_payment = fields.Date(related='payment_id.date')

    partner_id = fields.Many2one(related='payment_id.partner_id')
    destination_account_id = fields.Many2one(related='payment_id.destination_account_id')
    payment_move_ids = fields.One2many('account.payment.partial', 'wizard_id',
                                       string="Document Sale/Purchase",
                                       readonly=False)
    account_payable_or_receivable = fields.Many2one('account.move.line',
                                                    compute="compute_account_payable_or_receivable", store=True)

    #amount_total_current = fields.Monetary(compute="compute_amount_residual_account", currency_field='currency_id')
    amount_residual = fields.Monetary(compute="compute_amount_residual", currency_field='currency_id')

    @api.depends('payment_move_ids.partial_amount')
    def compute_amount_residual(self):
        for line in self.payment_move_ids:

            if line.currency_id.id != self.payment_id.currency_id.id:
                partial_amount = self.payment_id.currency_id._convert(
                    line.partial_amount,
                    line.company_id.currency_id,
                    line.company_id,
                    self.payment_id.date
                )
            else:
                partial_amount = line.partial_amount

            if line.move_id and abs(line.amount_residual_signed) < partial_amount:
                partial_amount_value = formatLang(self.env, self.currency_id.round(partial_amount), currency_obj=self.currency_id)
                residual = formatLang(self.env, self.currency_id.round(line.residual), currency_obj=self.currency_id)
                raise ValidationError(
                    _("Amount entered %s is greater than the invoice debt %s %s") % (partial_amount_value,
                                                                                     line.move_id.name,
                                                                                     residual))

        amount_residual = abs(self.account_payable_or_receivable.amount_residual_currency)
        sum_partial_amount = sum(self.payment_move_ids.mapped('partial_amount'))

        if amount_residual < sum_partial_amount:
            raise ValidationError(_("The sum of your partial amounts is greater than the remaining amount available."))
        self.amount_residual = abs(amount_residual) - abs(sum_partial_amount)

    @api.onchange('payment_type', 'partner_type', 'partner_id', 'currency_id')
    def _onchange_to_get_vendor_invoices(self):
        if self.payment_type in ['inbound', 'outbound'] and self.partner_type and self.partner_id and self.currency_id:
            self.payment_move_ids = [(6, 0, [])]
            if self.payment_type == 'inbound' and self.partner_type == 'customer':
                invoice_type = 'out_invoice'
            elif self.payment_type == 'outbound' and self.partner_type == 'customer':
                invoice_type = 'out_refund'
            elif self.payment_type == 'outbound' and self.partner_type == 'supplier':
                invoice_type = 'in_invoice'
            else:
                invoice_type = 'in_refund'
            move_recs = self.env['account.move'].search([
                ('partner_id', 'child_of', self.partner_id.id),
                ('state', '=', 'posted'),
                ('payment_state', 'in', ('not_paid', 'partial')),
                ('move_type', '=', invoice_type),
                ('currency_id', '=', self.currency_id.id)])

            payment_move_values = [(0, 0, {'move_id': line.id, 'payment_id': self.payment_id.id}) for line in move_recs]

            self.payment_move_ids = payment_move_values
    #---------------------------------------------------------------------
    # LOW-LEVEL METHODS
    # -------------------------------------------------------------------------
    @api.model
    def default_get(self, fields):
        result = super(AccountPaymentMultiPartialRegister, self).default_get(fields)
        # Linea move line
        context_payment_move_id = self._context.get('active_ids', [])

        result.update({
            'payment_id': context_payment_move_id,  # Pago account payment

        })
        return result

    def create_partial_payment(self, move_id, amount_partial):
        # Cuenta por cobrar o pagar de la factura
        to_reconcile = [self.account_payable_or_receivable]
        amount_partial = amount_partial
        # Factura activa a pagar
        payments = move_id
        domain = [('account_internal_type', 'in', ('receivable', 'payable'))]
        #to_reconcile_payments = [payments.line_ids.filtered_domain(domain)]
        signo = None
        if self.payment_type == 'inbound' and self.partner_type == 'customer':
            signo = -1
        if self.payment_type == 'outbound' and self.partner_type == 'customer':
            signo = 1
        if self.payment_type == 'inbound' and self.partner_type == 'supplier':
            signo = 1
        if self.payment_type == 'outbound' and self.partner_type == 'supplier':
            signo = -1

        for payment, lines in zip(payments, to_reconcile):

            payment_lines = payment.line_ids.filtered_domain(domain)
            payment_lines = payment_lines.with_context(amount=amount_partial, date=self.date_payment, signo=signo, multi_partial=True)
            for account in payment_lines.account_id:
                move_lines = (payment_lines + lines) \
                    .filtered_domain([('account_id', '=', account.id)])
                move_lines.reconcile()

        return True

    def _create_payments_partial(self):
        self.ensure_one()
        for record in self.payment_move_ids:
            if float_is_zero(record.partial_amount, precision_rounding=self.currency_id.rounding):
                continue
            #get el move id,  factura a la cual se le abonara el pago
            move_id = record.move_id
            # get el amount partial, captura el monto partial abonado
            amount_partial = 0.0

            if self.currency_id.id != move_id.company_currency_id.id:
                amount_partial = self.currency_id._convert(
                    record.partial_amount,
                    move_id.company_currency_id,
                    move_id.company_id,
                    self.date_payment
                )
            else:
                amount_partial = record.partial_amount

            self.create_partial_payment(move_id, amount_partial)
        return True

    def action_create_payments(self):
        action = {
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'view_mode': 'form',
            'res_id': self.payment_id.id,
        }

        if not self.payment_move_ids:
            return action

        if float_is_zero(sum(self.payment_move_ids.mapped('partial_amount')), precision_rounding=self.currency_id.rounding):
            raise ValidationError(_("All partial amounts is zero."))

        if self.amount_residual < 0:
            raise ValidationError(_("The sum of your partial amounts is greater than the remaining amount available."))

        payments = self._create_payments_partial()

        return action
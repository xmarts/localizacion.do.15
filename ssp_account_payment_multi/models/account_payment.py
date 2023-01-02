from odoo import _, api, fields, models


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    @api.depends('move_id')
    def compute_account_payable_or_receivable(self):
        domain = [('account_internal_type', 'in', ('receivable', 'payable'))]
        for payment in self:
            entries_lines = payment.move_id.line_ids.filtered_domain(domain)
            payment.account_payable_or_receivable = entries_lines.id

    def compute_amount_residual(self):
        for move_payment in self:
            amount_residual = move_payment.account_payable_or_receivable.amount_residual_currency
            move_payment.amount_residual = abs(amount_residual)

    account_payable_or_receivable = fields.Many2one('account.move.line', compute="compute_account_payable_or_receivable", store=False)
    matched_debit_ids = fields.One2many(related='account_payable_or_receivable.matched_debit_ids')
    matched_credit_ids = fields.One2many(related='account_payable_or_receivable.matched_credit_ids')
    amount_residual  = fields.Monetary(compute="compute_amount_residual", currency_field='currency_id')

    def action_register_multi_payment(self):

        return {
            'name': _('Register Multi Payment'),
            'res_model': 'account.payment.multi.partial.register',
            'view_mode': 'form',
            'context': {
                'active_model': 'account.payment',
                'active_ids': self.id,
            },
            'target': 'new',
            'type': 'ir.actions.act_window',
        }
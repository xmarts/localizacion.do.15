from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def _prepare_reconciliation_partials(self):
        partial_amount = self.env.context.get('amount', False)
        signo = self.env.context.get('signo', False)
        multi_partial = self.env.context.get('multi_partial', False)
        date_payment = self.env.context.get('date', False)
        res = super(AccountMoveLine, self)._prepare_reconciliation_partials()

        if multi_partial:

            for partial in res:
                debit_move_line_id = self.filtered(lambda line: line.balance > 0.0 or line.amount_currency > 0.0)
                credit_move_line_id = self.filtered(lambda line: line.balance < 0.0 or line.amount_currency < 0.0)

                boolean_debit_company_currency_id = debit_move_line_id.currency_id.id == debit_move_line_id.company_currency_id.id
                boolean_credit_company_currency_id = credit_move_line_id.currency_id.id == credit_move_line_id.company_currency_id.id

                credit_bank_cash = credit_move_line_id.move_id.journal_id.type in ('bank', 'cash')
                debit_bank_cash = debit_move_line_id.move_id.journal_id.type in ('bank', 'cash')

                #if boolean_debit_company_currency_id and boolean_credit_company_currency_id:
                partial.update({
                    'amount': partial_amount,
                    'debit_amount_currency': partial_amount,
                    'credit_amount_currency': partial_amount,
                })

                if not boolean_credit_company_currency_id:
                    credit_amount_currency = credit_move_line_id.company_currency_id._convert(
                        partial_amount,
                        credit_move_line_id.currency_id,
                        credit_move_line_id.company_id,
                        credit_move_line_id.date if credit_bank_cash else debit_move_line_id.date,
                    )
                    partial.update({
                        'credit_amount_currency': credit_amount_currency,
                    })

                if not boolean_debit_company_currency_id:
                    debit_amount_currency = debit_move_line_id.company_currency_id._convert(
                        partial_amount,
                        debit_move_line_id.currency_id,
                        debit_move_line_id.company_id,
                        debit_move_line_id.date if debit_bank_cash else credit_move_line_id.date,
                    )
                    partial.update({
                        'debit_amount_currency': debit_amount_currency,
                    })

        return res
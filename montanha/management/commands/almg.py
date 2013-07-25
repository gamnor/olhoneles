# -*- coding: utf-8 -*-
#
# Copyright (©) 2010-2013 Estêvão Samuel Procópio
# Copyright (©) 2010-2013 Gustavo Noronha Silva
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as
#  published by the Free Software Foundation, either version 3 of the
#  License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.

import json
import re
from basecollector import BaseCollector
from datetime import datetime, date
from montanha.models import *


class ALMG(BaseCollector):
    def __init__(self, debug_enabled=False, full_scan=False, mandate_start=date(2011, 1, 1)):
        self.debug_enabled = debug_enabled
        self.full_scan = full_scan
        self.mandate_start = mandate_start
        try:
            self.institution = Institution.objects.get(siglum='ALMG')
        except Institution.DoesNotExist:
            self.institution = Institution(siglum='ALMG', name=u'Assembléia Legislativa do Estado de Minas Gerais')
            self.institution.save()

    def post_process_uri(self, contents):
        # The JSON returned by ALMG's web service uses the brazilian
        # locale for floating point numbers (uses , instead of .).
        data = re.sub(r"([0-9]+),([0-9]+)", r"\1.\2", contents)

        return json.loads(data)

    def update_legislators(self):
        legislators = self.retrieve_uri("http://dadosabertos.almg.gov.br/ws/deputados/em_exercicio?formato=json")["list"]
        for entry in legislators:
            try:
                legislator = Legislator.objects.get(original_id=entry["id"])
                self.debug("Found existing legislator: %s" % unicode(legislator))

                try:
                    mandate = Mandate.objects.get(legislator=legislator, date_start=self.mandate_start)
                except Mandate.DoesNotExist:
                    mandate = Mandate(legislator=legislator, date_start=self.mandate_start, party=party, institution=self.institution)
                    mandate.save()
                    self.debug("Mandate starting on %s did not exist, created." % self.mandate_start.strftime("%F"))

            except Legislator.DoesNotExist:
                legislator = Legislator(name=entry["nome"], original_id=entry["id"])
                legislator.save()

                try:
                    party = PoliticalParty.objects.get(siglum=entry["partido"])
                except PoliticalParty.DoesNotExist:
                    party = PoliticalParty(siglum=entry["partido"])
                    party.save()

                    self.debug("New party: %s" % unicode(party))

                mandate = Mandate(legislator=legislator, date_start=self.mandate_start, party=party, institution=self.institution)
                mandate.save()

                self.debug("New legislator found: %s" % unicode(legislator))

    def update_data_for_month(self, mandate, year, month):
        self.debug("Updating data for %d-%d - %s" % (year, month, unicode(mandate)))
        uri = "http://dadosabertos.almg.gov.br/ws/prestacao_contas/verbas_indenizatorias/deputados/%s/%d/%d?formato=json" % (mandate.legislator.original_id, year, month)
        for entry in self.retrieve_uri(uri)["list"]:
            try:
                nature = ExpenseNature.objects.get(original_id=entry["codTipoDespesa"])
            except ExpenseNature.DoesNotExist:
                nature = ExpenseNature(original_id=entry["codTipoDespesa"], name=entry["descTipoDespesa"])
                nature.save()

            for details in entry["listaDetalheVerba"]:
                try:
                    supplier = Supplier.objects.get(identifier=details["cpfCnpj"])
                except Supplier.DoesNotExist:
                    supplier = Supplier(identifier=details["cpfCnpj"], name=details["nomeEmitente"])
                    supplier.save()

                if "descDocumento" in details:
                    number = details["descDocumento"]
                else:
                    self.debug("No document number, using reference date.")
                    number = details["dataReferencia"]["$"]

                date = details["dataEmissao"]["$"]
                value = details["valorDespesa"]
                expensed = details["valorReembolsado"]

                try:
                    expense = Expense.objects.get(original_id=details["id"],
                                                  number=number,
                                                  nature=nature,
                                                  date=date,
                                                  value=value,
                                                  expensed=expensed,
                                                  mandate=mandate,
                                                  supplier=supplier)
                    self.debug("Existing expense found: %s" % unicode(expense))
                except Expense.DoesNotExist:
                    expense = Expense(original_id=details["id"],
                                      number=number,
                                      nature=nature,
                                      date=date,
                                      value=value,
                                      expensed=expensed,
                                      mandate=mandate,
                                      supplier=supplier)
                    expense.save()

                    self.debug("New expense found: %s" % unicode(expense))

# -*- coding: utf-8 -*-
# Copyright 2016-2018  Flensburg University of Applied Sciences,
# Europa-Universität Flensburg,
# Centre for Sustainable Energy Systems,
# DLR-Institute for Networked Energy Systems

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation; either version 3 of the
# License, or (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# File description
"""
This is the application file for the tool eTraGo.
Define your connection parameters and power flow settings before executing
the function etrago.
"""


import datetime
import os
import os.path
import time
from etrago.tools.utilities import get_args_setting

__copyright__ = (
    "Flensburg University of Applied Sciences, "
    "Europa-Universität Flensburg, Centre for Sustainable Energy Systems, "
    "DLR-Institute for Networked Energy Systems")
__license__ = "GNU Affero General Public License Version 3 (AGPL-3.0)"
__author__ = "ulfmueller, lukasol, wolfbunke, mariusves, s3pp"


if 'READTHEDOCS' not in os.environ:
    # Sphinx does not run this code.
    # Do not import internal packages directly

    from etrago.network import Etrago
    from etrago.sectors.heat import _try_add_heat_sector
    from etrago.cluster.disaggregation import (
            MiniSolverDisaggregation,
            UniformDisaggregation)

    from etrago.cluster.networkclustering import (
        busmap_from_psql,
        cluster_on_extra_high_voltage,
        kmean_clustering)

    from etrago.tools.utilities import (
        pf_post_lopf,
        calc_line_losses,
        geolocation_buses,
        get_args_setting,
        iterate_lopf)

    from etrago.tools.constraints import(
        Constraints)

    from etrago.tools.extendable import (
            print_expansion_costs)

    from etrago.cluster.snapshot import snapshot_clustering

    import oedialect


args = {
    # Setup and Configuration:
    'db': 'local',  # database session
    'gridversion': 'v0.4.6',  # None for model_draft or Version number
    'method': 'lopf',  # lopf or pf
    'pf_post_lopf': False,  # perform a pf after a lopf simulation
    'start_snapshot': 1,
    'end_snapshot': 168,
    'solver': 'gurobi',  # glpk, cplex or gurobi
    'solver_options': {'BarConvTol': 1.e-5, 'FeasibilityTol': 1.e-5,
                       'method':2, 'crossover':0,
                       'logFile': 'solver.log'},  # {} for default options
    'model_formulation': 'kirchhoff', # angles or kirchhoff
    'scn_name': 'NEP 2035',  # a scenario: Status Quo, NEP 2035, eGo 100
    'add_sectors': [],
    # Scenario variations:
    'scn_extension': None,  # None or array of extension scenarios
    'scn_decommissioning': None,  # None or decommissioning scenario
    # Export options:
    'lpfile': False,  # save pyomo's lp file: False or /path/tofolder
    'csv_export': 'test_2007_nmp',  # save results as csv: False or /path/tofolder
    # Settings:
    'extendable': ['network', 'storage'],  # Array of components to optimize
    'generator_noise': 789456,  # apply generator noise, False or seed number
    'extra_functionality': {},  # Choose function name or {}
    # Clustering:
    'network_clustering_kmeans': 100,  # False or the value k for clustering
    'kmeans_busmap': 'kmeans_busmap_100_result.csv',  # False or predefined busmap for k-means
    'network_clustering_ehv': False,  # clustering of HV buses to EHV buses.
    'disaggregation': None,  # None, 'mini' or 'uniform'
    'snapshot_clustering': False,  # False or the number of 'periods'
    # Simplifications:
    'skip_snapshots': False,
    'branch_capacity_factor': {'HV': 0.5, 'eHV': 0.7},  # p.u. branch derating
    'load_shedding': False,  # meet the demand at value of loss load cost
    'foreign_lines': {'carrier': 'AC', 'capacity': 'osmTGmod'},
    'comments': None}

args = get_args_setting(args, jsonpath=None)


def etrago(args):
    """The etrago function works with following arguments:


    Parameters
    ----------

    db : str
        ``'oedb'``,
        Name of Database session setting stored in *config.ini* of *.egoio*

    gridversion : NoneType or str
        ``'v0.2.11'``,
        Name of the data version number of oedb: state ``'None'`` for
        model_draft (sand-box) or an explicit version number
        (e.g. 'v0.2.10') for the grid schema.

    method : str
        ``'lopf'``,
        Choose between a non-linear power flow ('pf') or
        a linear optimal power flow ('lopf').

    pf_post_lopf : bool
        False,
        Option to run a non-linear power flow (pf) directly after the
        linear optimal power flow (and thus the dispatch) has finished.

    start_snapshot : int
        1,
        Start hour of the scenario year to be calculated.

    end_snapshot : int
        2,
        End hour of the scenario year to be calculated.

    solver : str
        'glpk',
        Choose your preferred solver. Current options: 'glpk' (open-source),
        'cplex' or 'gurobi'.

    solver_options: dict
        Choose settings of solver to improve simulation time and result. 
        Options are described in documentation of choosen solver.
    
    model_formulation: str
        'angles'
        Choose formulation of pyomo-model.
        Current options: angles, cycles, kirchhoff, ptdf

    scn_name : str
        'Status Quo',
        Choose your scenario. Currently, there are three different
        scenarios: 'Status Quo', 'NEP 2035', 'eGo100'. If you do not
        want to use the full German dataset, you can use the excerpt of
        Schleswig-Holstein by adding the acronym SH to the scenario
        name (e.g. 'SH Status Quo').

   scn_extension : NoneType or list
       None,
       Choose extension-scenarios which will be added to the existing
       network container. Data of the extension scenarios are located in
       extension-tables (e.g. model_draft.ego_grid_pf_hv_extension_bus)
       with the prefix 'extension_'.
       Currently there are three overlay networks:
           'nep2035_confirmed' includes all planed new lines confirmed by the
           Bundesnetzagentur
           'nep2035_b2' includes all new lines planned by the
           Netzentwicklungsplan 2025 in scenario 2035 B2
           'BE_NO_NEP 2035' includes planned lines to Belgium and Norway and
           adds BE and NO as electrical neighbours

    scn_decommissioning : str
        None,
        Choose an extra scenario which includes lines you want to decommise
        from the existing network. Data of the decommissioning scenarios are
        located in extension-tables
        (e.g. model_draft.ego_grid_pf_hv_extension_bus) with the prefix
        'decommissioning_'.
        Currently, there are two decommissioning_scenarios which are linked to
        extension-scenarios:
            'nep2035_confirmed' includes all lines that will be replaced in
            confirmed projects
            'nep2035_b2' includes all lines that will be replaced in
            NEP-scenario 2035 B2

    lpfile : obj
        False,
        State if and where you want to save pyomo's lp file. Options:
        False or '/path/tofolder'.import numpy as np

    csv_export : obj
        False,
        State if and where you want to save results as csv files.Options:
        False or '/path/tofolder'.

    extendable : list
        ['network', 'storages'],
        Choose components you want to optimize.
        Settings can be added in /tools/extendable.py.
        The most important possibilities:
            'network': set all lines, links and transformers extendable
            'german_network': set lines and transformers in German grid
                            extendable
            'foreign_network': set foreign lines and transformers extendable
            'transformers': set all transformers extendable
            'overlay_network': set all components of the 'scn_extension'
                               extendable
            'storages': allow to install extendable storages
                        (unlimited in size) at each grid node in order to meet
                        the flexibility demand.
            'network_preselection': set only preselected lines extendable,
                                    method is chosen in function call


    generator_noise : bool or int
        State if you want to apply a small random noise to the marginal costs
        of each generator in order to prevent an optima plateau. To reproduce
        a noise, choose the same integer (seed number).

    extra_functionality : dict or None
        None,
        Choose extra functionalities and their parameters for PyPSA-model.
        Settings can be added in /tools/constraints.py.
        Current options are:
            'max_line_ext': float
                Maximal share of network extension in p.u.
            'min_renewable_share': float
                Minimal share of renewable generation in p.u.
            'cross_border_flow': array of two floats
                Limit cross-border-flows between Germany and its neigbouring
                countries, set values in p.u. of german loads in snapshots
                for all countries
                (positiv: export from Germany)
            'cross_border_flows_per_country': dict of cntr and array of floats
                Limit cross-border-flows between Germany and its neigbouring
                countries, set values in p.u. of german loads in snapshots
                for each country
                (positiv: export from Germany)  
            'max_curtailment_per_gen': float
                Limit curtailment of all wind and solar generators in Germany,
                values set in p.u. of generation potential.
            'max_curtailment_per_gen': float
                Limit curtailment of each wind and solar generator in Germany,
                values set in p.u. of generation potential.
            'capacity_factor': dict of arrays
                Limit overall energy production for each carrier, 
                set upper/lower limit in p.u.
            'capacity_factor_per_gen': dict of arrays
                Limit overall energy production for each generator by carrier, 
                set upper/lower limit in p.u.
            'capacity_factor_per_cntr': dict of dict of arrays
                Limit overall energy production country-wise for each carrier, 
                set upper/lower limit in p.u.
            'capacity_factor_per_gen_cntr': dict of dict of arrays
                Limit overall energy production country-wise for each generator 
                by carrier, set upper/lower limit in p.u.

    network_clustering_kmeans : bool or int
        False,
        State if you want to apply a clustering of all network buses down to
        only ``'k'`` buses. The weighting takes place considering generation
        and load
        at each node. If so, state the number of k you want to apply. Otherwise
        put False. This function doesn't work together with
        ``'line_grouping = True'``.

    load_cluster : bool or obj
        state if you want to load cluster coordinates from a previous run:
        False or /path/tofile (filename similar to ./cluster_coord_k_n_result).

    network_clustering_ehv : bool
        False,
        Choose if you want to cluster the full HV/EHV dataset down to only the
        EHV buses. In that case, all HV buses are assigned to their closest EHV
        sub-station, taking into account the shortest distance on power lines.

    snapshot_clustering : bool or int
        False,
        State if you want to cluster the snapshots and run the optimization
        only on a subset of snapshot periods. The int value defines the number
        of periods (i.e. days) which will be clustered to.
        Move to PyPSA branch:features/snapshot_clustering

    branch_capacity_factor : dict
        {'HV': 0.5, 'eHV' : 0.7},
        Add a factor here if you want to globally change line capacities
        (e.g. to "consider" an (n-1) criterion or for debugging purposes).

    load_shedding : bool
        False,
        State here if you want to make use of the load shedding function which
        is helpful when debugging: a very expensive generator is set to each
        bus and meets the demand when regular
        generators cannot do so.

    foreign_lines : dict
        {'carrier':'AC', 'capacity': 'osmTGmod}'
        Choose transmission technology and capacity of foreign lines:
            'carrier': 'AC' or 'DC'
            'capacity': 'osmTGmod', 'ntc_acer' or 'thermal_acer'

    comments : str
        None

    Returns
    -------
    network : `pandas.DataFrame<dataframe>`
        eTraGo result network based on `PyPSA network
        <https://www.pypsa.org/doc/components.html#network>`_
    """
    etrago = Etrago(args)

    clustering = None

    # ehv network clustering
    if args['network_clustering_ehv']:
        etrago.network.generators.control = "PV"
        busmap = busmap_from_psql(etrago)
        etrago.network = cluster_on_extra_high_voltage(
            etrago.network, busmap, with_time=True)

    # k-mean clustering
    if not args['network_clustering_kmeans'] == False:
        etrago.network.generators.control = "PV"
        clustering = kmean_clustering(
                etrago,
                line_length_factor=1,
                remove_stubs=False,
                use_reduced_coordinates=False,
                bus_weight_tocsv=None,
                bus_weight_fromcsv=None,
                n_init=10,
                max_iter=100,
                tol=1e-6,
                n_jobs=-1)
        if args['disaggregation']!=None:
            etrago.disaggregated_network = etrago.network.copy()
        etrago.network = clustering.network.copy()
        etrago.network.generators.control[etrago.network.generators.control==''] = 'PV'
        geolocation_buses(etrago)

    if 'heat' in args['add_sectors']:
        _try_add_heat_sector(etrago)

    # skip snapshots
    if args['skip_snapshots']:
        etrago.network.snapshots = etrago.network.snapshots[::args['skip_snapshots']]
        etrago.network.snapshot_weightings = etrago.network.snapshot_weightings[
            ::args['skip_snapshots']] * args['skip_snapshots']

    # snapshot clustering
    if not args['snapshot_clustering'] is False:
        etrago.network = snapshot_clustering(etrago, how='daily')
        args['snapshot_clustering_constraints'] = 'soc_constraints'

    # start linear optimal powerflow calculations
    if args['method'] == 'lopf':
        x = time.time()
        try: 
            from vresutils.benchmark import memory_logger
            with memory_logger(filename=args['csv_export']+'_memory.log', interval=30.) as mem:
                iterate_lopf(etrago,
                              Constraints(args).functionality,
                              method={'n_iter':5, 'pyomo':False})
        except:
            iterate_lopf(etrago,
                              Constraints(args).functionality,
                              method={'n_iter':5, 'pyomo':True})
        y = time.time()
        z = (y - x) / 60
        print("Maximum memory usage: {} MB".format(mem.mem_usage[0]))
        print("Total time for LOPF [min]:", round(z, 2))

    elif args['method'] == 'ilopf':
        from pypsa.linopf import ilopf
        # Temporary set all line types 
        etrago.network.lines.type = 'Al/St 240/40 4-bundle 380.0'
        x = time.time()
        ilopf(etrago.network, solver_name = args['solver'], 
              solver_options = args['solver_options'])
        y = time.time()
        z = (y - x) / 60
        print("Time for LOPF [min]:", round(z, 2))
        
    etrago._calc_etrago_results()
    
    if args['pf_post_lopf'] and args['add_sectors']==[]:
        pf_post_lopf(etrago,
                     add_foreign_lopf=True,
                     q_allocation='p_nom',
                     calc_losses=True)
        calc_line_losses(etrago.network)


    if not args['extendable'] == []:
        print_expansion_costs(etrago.network, args)

    if clustering:
        disagg = args.get('disaggregation')
        skip = () if args['pf_post_lopf'] else ('q',)
        t = time.time()
        if disagg:
            if disagg == 'mini':
                disaggregation = MiniSolverDisaggregation(
                        etrago.disaggregated_network,
                        etrago.network,
                        clustering,
                        skip=skip)
            elif disagg == 'uniform':
                disaggregation = UniformDisaggregation(etrago.disaggregated_network,
                                                       etrago.network,
                                                       clustering,
                                                       skip=skip)

            else:
                raise Exception('Invalid disaggregation command: ' + disagg)

            disaggregation.execute(etrago.scenario, solver=args['solver'])
            # temporal bug fix for solar generator which ar during night time
            # nan instead of 0
            etrago.disaggregated_network.generators_t.p.fillna(0, inplace=True)
            etrago.disaggregated_network.generators_t.q.fillna(0, inplace=True)

            etrago.disaggregated_network.results = etrago.network.results
            print("Time for overall desaggregation [min]: {:.2}"
                .format((time.time() - t) / 60))

    # close session
    # session.close()

    return etrago


if __name__ == '__main__':
    # execute etrago function
    print(datetime.datetime.now())
    etrago = etrago(args)
    print(datetime.datetime.now())
    # plots
    # make a line loading plot
    # plot_line_loading(network)
    # plot stacked sum of nominal power for each generator type and timestep
    # plot_stacked_gen(network, resolution="MW")
    # plot to show extendable storages
    # storage_distribution(network)
    # extension_overlay_network(network)
